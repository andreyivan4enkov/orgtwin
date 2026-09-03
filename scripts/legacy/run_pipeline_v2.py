#!/usr/bin/env python3
"""
Пайплайн v2: softmax + Ridge(log1p(dt)) + полный дамп констант/неудач в LAB_JOURNAL.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin.config.constants import DEFAULT, ExperimentConfig
from orgtwin.decompose.dof import degrees_of_freedom_report
from orgtwin.eval.score import actual_case_durations, evaluate
from orgtwin.ingest.xes_loader import fit_holdout_split, load_event_table
from orgtwin.policy.softmax import prune_membrane_actions, train_softmax_policies
from orgtwin.policy.timing import (
    predict_case_durations,
    train_case_duration_model,
    train_timing_model,
)
from orgtwin.sim.engine import build_org_from_policy, simulate
import numpy as np
import pandas as pd


def main() -> None:
    # без буфера — иначе при долгом fit кажется, что процесс завис
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    cfg = ExperimentConfig()  # все константы явны
    xes = ROOT / "data" / "raw" / "BPI_Challenge_2012.xes"
    derived = ROOT / "data" / "derived"
    reports = ROOT / "reports"
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    decisions: list[str] = []

    (derived / "experiment_config_v2.json").write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    decisions.append("Все гиперпараметры сериализованы в experiment_config_v2.json")

    print("Загрузка XES…")
    df = load_event_table(xes)
    print(
        f"  событий={len(df)} кейсов={df['case:concept:name'].nunique()} "
        f"агентов={df['org:resource'].nunique()}"
    )

    fit, hold, split_meta = fit_holdout_split(
        df, fit_months=cfg.split.fit_months, holdout_months=cfg.split.holdout_months
    )
    if cfg.split.fit_months != cfg.split.target_fit_months:
        failures.append(
            {
                "id": "SPLIT_NOT_7_3",
                "severity": "critical_limitation",
                "detail": (
                    f"Донор ~5.5 мес → используем {cfg.split.fit_months}+{cfg.split.holdout_months}, "
                    f"не целевые {cfg.split.target_fit_months}+{cfg.split.target_holdout_months}"
                ),
            }
        )

    print("Обучение softmax…")
    policy = train_softmax_policies(
        fit,
        lambda_entropy=cfg.policy.lambda_entropy,
        max_iter=cfg.policy.max_iter,
        random_state=cfg.policy.random_state,
        solver=cfg.policy.solver,
        tol=cfg.policy.tol,
        C=cfg.policy.C,
    )
    decisions.append(
        f"Softmax solver={cfg.policy.solver} tol={cfg.policy.tol} CE+λH λ={cfg.policy.lambda_entropy} "
        f"C={cfg.policy.C} max_iter={cfg.policy.max_iter}"
    )

    prune_info = prune_membrane_actions(
        policy, fit, lambda_entropy=cfg.policy.lambda_entropy, min_support=cfg.policy.prune_min_support
    )
    decisions.append(f"Прунинг min_support={cfg.policy.prune_min_support}")
    if prune_info.get("pruned_actions_by_role"):
        failures.append(
            {
                "id": "PRUNE_MAY_BIAS_TERMINALS",
                "severity": "risk",
                "detail": f"Срезаны Action: {prune_info['pruned_actions_by_role']} — риск смещения исходов",
            }
        )

    print("Обучение timing Ridge(log1p(dt))…")
    timing = train_timing_model(fit, policy, cfg=cfg.timing)
    print(
        f"  timing fit spearman={timing.train_metrics.get('fit_spearman')} "
        f"vs median baseline={timing.train_metrics.get('baseline_median_agent_action_spearman')}"
    )
    decisions.append(
        f"Ridge alpha={cfg.timing.ridge_alpha}; latency_noise=[{cfg.timing.latency_noise_low},{cfg.timing.latency_noise_high}] (выкл)"
    )
    if timing.train_metrics.get("fit_spearman", 0) < 0.3:
        failures.append(
            {
                "id": "TIMING_FIT_WEAK",
                "severity": "warning",
                "detail": f"Даже на fit Spearman dt={timing.train_metrics.get('fit_spearman')} — потолок предсказуемости dt",
            }
        )

    print("Обучение case-level duration head…")
    case_dur_model = train_case_duration_model(fit, policy, cfg=cfg.timing)
    print(f"  case_dur fit spearman={case_dur_model.train_metrics.get('fit_spearman')}")
    decisions.append(
        "Добавлена case-level Ridge-голова длительности (не эмерджентная сумма dt) — "
        "после провала sum(dt) Spearman≈0 при fit_dt Spearman~0.85"
    )
    failures.append(
        {
            "id": "MAX_STEPS_80_ABORTED",
            "severity": "incident",
            "detail": (
                "Прогон max_steps=80 прерван: wall-time (поштучный softmax encode на каждом шаге). "
                "Частичный результат max_steps=40: dur_spearman≈-0.001, hit_max=738/5658, next_acc≈0.55. "
                "В финальном v2 оставляем только max_steps=40 + case-level duration head."
            ),
        }
    )

    graph = build_org_from_policy(fit, policy, donor_id=cfg.donor_id)
    dof = degrees_of_freedom_report(graph)

    results = {}
    for steps in (40,):  # 80 отменён — см. MAX_STEPS_80_ABORTED
        print(f"Симуляция holdout max_steps={steps}…")
        sim = simulate(
            graph, hold, policy=policy, timing=timing, cfg=cfg, max_steps_per_case=steps, seed=cfg.sim.seed
        )
        report = evaluate(hold, sim, policy=policy)
        # case-level duration metric (отдельная голова)
        pred_dur = predict_case_durations(case_dur_model, hold, policy)
        actual_dur = actual_case_durations(hold)
        common = [c for c in pred_dur if c in actual_dur]
        ad = np.array([actual_dur[c] for c in common], dtype=float)
        pd_ = np.array([pred_dur[c] for c in common], dtype=float)
        case_head_spearman = float(pd.Series(ad).corr(pd.Series(pd_), method="spearman"))
        case_head_log_mae = float(np.mean(np.abs(np.log1p(ad) - np.log1p(pd_))))
        report.metrics["case_level_head_spearman"] = case_head_spearman
        report.metrics["case_level_head_log_mae"] = case_head_log_mae
        report.metrics["case_level_head_n"] = len(common)
        results[str(steps)] = {
            "metrics": report.metrics,
            "sim_meta": sim.meta,
        }
        print(
            f"  steps={steps} emergent_dur_spearman={report.metrics.get('case_duration_spearman')} "
            f"case_head_spearman={case_head_spearman} "
            f"hit_max={sim.meta.get('n_hit_max_steps')} "
            f"next_acc={report.metrics.get('holdout_next_step_accuracy')}"
        )
        if sim.meta.get("n_hit_max_steps", 0) > 0.2 * sim.meta.get("n_cases", 1):
            failures.append(
                {
                    "id": f"MAX_STEPS_BINDING_{steps}",
                    "severity": "warning",
                    "detail": (
                        f"{sim.meta['n_hit_max_steps']}/{sim.meta['n_cases']} кейсов упёрлись в max_steps={steps}"
                    ),
                }
            )

    best_key = "40"
    best = results[best_key]
    decisions.append("Для run_v2.md max_steps=40 (80 aborted)")

    if (best["metrics"].get("case_duration_spearman") or 0) < 0.2:
        failures.append(
            {
                "id": "EMERGENT_DURATION_SPEARMAN_BELOW_0_2",
                "severity": "failure",
                "detail": (
                    f"Эмерджентная сумма dt: Spearman={best['metrics'].get('case_duration_spearman')}. "
                    f"Case-level head Spearman={best['metrics'].get('case_level_head_spearman')}. "
                    "Вывод: хороший event-dt ≠ хороший case wall-clock через симулированную траекторию Action."
                ),
            }
        )
    if (best["metrics"].get("case_level_head_spearman") or 0) >= 0.2:
        decisions.append(
            f"Case-level duration head закрывает порог Spearman>0.2 "
            f"({best['metrics'].get('case_level_head_spearman'):.3f}) — но это НЕ эмерджентность"
        )

    if (best["metrics"].get("holdout_next_step_top3") or 0) < 0.85:
        failures.append(
            {
                "id": "TOP3_REGRESSION",
                "severity": "failure",
                "detail": f"top3={best['metrics'].get('holdout_next_step_top3')} < 0.85",
            }
        )

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict(),
        "split_meta": split_meta,
        "train_policy": policy.train_metrics,
        "train_timing": timing.train_metrics,
        "train_case_duration": case_dur_model.train_metrics,
        "prune": prune_info,
        "dof": dof,
        "results_by_max_steps": results,
        "selected_max_steps": best_key,
        "decisions": decisions,
        "failures": failures,
    }
    (reports / "run_v2_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (reports / "holdout_metrics_v2.json").write_text(
        json.dumps(best["metrics"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / "timing_metrics.json").write_text(
        json.dumps(timing.train_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / "failures_v2.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = render_md(payload)
    (reports / "run_v2.md").write_text(md, encoding="utf-8")
    append_lab_journal(reports / "LAB_JOURNAL.md", payload)
    print(md)
    print("\nГотово → reports/run_v2.md + LAB_JOURNAL.md")


def render_md(payload: dict) -> str:
    best = payload["results_by_max_steps"][payload["selected_max_steps"]]
    fail_lines = "\n".join(
        f"- **{f['id']}** ({f['severity']}): {f['detail']}" for f in payload["failures"]
    ) or "- (нет)"
    dec_lines = "\n".join(f"- {d}" for d in payload["decisions"])
    return f"""# Прогон v2 — softmax + Ridge(dt)

## Константы
См. `data/derived/experiment_config_v2.json` и `src/orgtwin/config/constants.py`.

Ключевые:
- λ_entropy={payload['config']['policy']['lambda_entropy']}
- prune_min_support={payload['config']['policy']['prune_min_support']}
- ridge_alpha={payload['config']['timing']['ridge_alpha']}
- latency_noise=[{payload['config']['timing']['latency_noise_low']}, {payload['config']['timing']['latency_noise_high']}]
- max_steps выбран={payload['selected_max_steps']} (сравнивали 40 и 80)
- split={payload['config']['split']['fit_months']}+{payload['config']['split']['holdout_months']} (цель 7+3)

## Timing fit (event dt)
```json
{json.dumps(payload['train_timing'], ensure_ascii=False, indent=2)}
```

## Case-level duration head (НЕ эмерджентность)
```json
{json.dumps(payload.get('train_case_duration', {}), ensure_ascii=False, indent=2)}
```

## Holdout (selected max_steps={payload['selected_max_steps']})
```json
{json.dumps(best['metrics'], ensure_ascii=False, indent=2)}
```

## Sim meta
```json
{json.dumps(best['sim_meta'], ensure_ascii=False, indent=2)}
```

## max_steps
Только 40 в финальном прогоне; 80 aborted (см. failures).
```json
{json.dumps({k: {'emergent_dur_spearman': v['metrics'].get('case_duration_spearman'), 'case_head_spearman': v['metrics'].get('case_level_head_spearman'), 'hit_max': v['sim_meta'].get('n_hit_max_steps'), 'sim_events': v['metrics'].get('sim_events')} for k,v in payload['results_by_max_steps'].items()}, ensure_ascii=False, indent=2)}
```

## Решения
{dec_lines}

## Неудачи / риски / ограничения
{fail_lines}
"""


def append_lab_journal(path: Path, payload: dict) -> None:
    best = payload["results_by_max_steps"][payload["selected_max_steps"]]
    block = f"""

---

## v2 — факт прогона ({payload['timestamp_utc']})

### Что изменили относительно v1
- Модель dt: Ridge(log1p(dt) | prev, action, agent, amount_bin), alpha={payload['config']['timing']['ridge_alpha']}
- latency_noise выключен (=1.0); в v1 было U(0.7,1.3) — зафиксировано как вероятная причина Spearman≈0
- Прогон max_steps ∈ {{40, 80}}; выбран {payload['selected_max_steps']}
- Константы вынесены в `config/constants.py` + дамп JSON

### Timing fit
- event-dt spearman={payload['train_timing'].get('fit_spearman')}
- baseline median(agent,action) spearman={payload['train_timing'].get('baseline_median_agent_action_spearman')}
- case-level head fit spearman={payload.get('train_case_duration', {}).get('fit_spearman')}

### Holdout (selected)
- next-step acc={best['metrics'].get('holdout_next_step_accuracy')}
- top3={best['metrics'].get('holdout_next_step_top3')}
- weekly_corr={best['metrics'].get('weekly_events_corr')}
- emergent duration Spearman={best['metrics'].get('case_duration_spearman')}
- case-level head Spearman={best['metrics'].get('case_level_head_spearman')}
- hit_max_steps={best['sim_meta'].get('n_hit_max_steps')}/{best['sim_meta'].get('n_cases')}

### Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

### Неудачи / риски
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures']) or '- нет'}

### Артефакты
- `reports/run_v2.md`, `reports/run_v2_full.json`, `reports/holdout_metrics_v2.json`
- `data/derived/failures_v2.json`, `experiment_config_v2.json`, `timing_metrics.json`
"""
    with path.open("a", encoding="utf-8") as f:
        f.write(block)


if __name__ == "__main__":
    main()
