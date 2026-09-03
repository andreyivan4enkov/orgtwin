#!/usr/bin/env python3
"""
OrgTwin v0.4.0 — батч-сима + калибровка длительности + стресс (топ-агенты выключены).

Версия зафиксирована в VERSION / pyproject.toml / orgtwin.__version__.
Артефакты только с суффиксом v0.4.0 — старые reports не переписываем.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from orgtwin import __version__
from orgtwin.config.constants import ExperimentConfig
from orgtwin.decompose.dof import degrees_of_freedom_report
from orgtwin.eval.score import actual_case_durations, evaluate
from orgtwin.ingest.xes_loader import fit_holdout_split, load_event_table
from orgtwin.policy.softmax import prune_membrane_actions, train_softmax_policies
from orgtwin.policy.timing import (
    predict_case_durations,
    train_case_duration_model,
    train_timing_model,
)
from orgtwin.sim.engine import (
    build_org_from_policy,
    disable_agents,
    simulate_batch,
    top_agents_by_workload,
)

VER = "0.4.0"
assert __version__ == VER, f"VERSION mismatch package={__version__} script={VER}"


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    cfg = ExperimentConfig()
    xes = ROOT / "data" / "raw" / "BPI_Challenge_2012.xes"
    derived = ROOT / "data" / "derived"
    reports = ROOT / "reports"
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    decisions: list[str] = [
        f"Релиз OrgTwin {VER}: батч-encode, калибровка dt→case-head, stress top-3 агентов",
        "Старые run_v0/v1/v2 не перезаписываем",
    ]

    print(f"OrgTwin {VER}")
    print("Загрузка XES…")
    t0 = time.perf_counter()
    df = load_event_table(xes)
    print(f"  событий={len(df)} агентов={df['org:resource'].nunique()} ({time.perf_counter()-t0:.1f}s)")

    fit, hold, split_meta = fit_holdout_split(
        df, fit_months=cfg.split.fit_months, holdout_months=cfg.split.holdout_months
    )
    failures.append(
        {
            "id": "SPLIT_NOT_7_3",
            "severity": "critical_limitation",
            "detail": f"split {cfg.split.fit_months}+{cfg.split.holdout_months}, цель 7+3",
        }
    )

    print("Обучение softmax…")
    t1 = time.perf_counter()
    # A/B: оставляем saga как в 0.3; отдельный прогон lbfgs — будущий 0.4.1
    policy = train_softmax_policies(
        fit,
        lambda_entropy=cfg.policy.lambda_entropy,
        max_iter=cfg.policy.max_iter,
        random_state=cfg.policy.random_state,
        solver=cfg.policy.solver,
        tol=cfg.policy.tol,
        C=cfg.policy.C,
    )
    decisions.append(f"solver={cfg.policy.solver} (A/B lbfgs отложен на 0.4.1)")
    print(f"  fit_acc={policy.train_metrics['fit_action_accuracy']:.3f} ({time.perf_counter()-t1:.1f}s)")

    # В 0.4.0 НЕ пруним O_DECLINED-класс риска: prune с повышенным min_support или skip decline
    prune_info = prune_membrane_actions(
        policy, fit, lambda_entropy=cfg.policy.lambda_entropy, min_support=cfg.policy.prune_min_support
    )
    # откат прунинга O_DECLINED если срезали
    restored = []
    for role, acts in list(prune_info.get("pruned_actions_by_role", {}).items()):
        for a in acts:
            if "DECLINED" in a and a in policy.action_classes:
                idx = policy.action_classes.index(a)
                policy.role_action_mask[role][idx] = True
                restored.append(f"{role}:{a}")
    if restored:
        decisions.append(f"Откат прунинга DECLINED: {restored}")
        failures.append(
            {
                "id": "PRUNE_DECLINED_ROLLED_BACK",
                "severity": "decision",
                "detail": f"Восстановлены на мембране: {restored} (риск PRUNE_MAY_BIAS_TERMINALS из 0.3.0)",
            }
        )

    timing = train_timing_model(fit, policy, cfg=cfg.timing)
    case_head = train_case_duration_model(fit, policy, cfg=cfg.timing)
    targets = predict_case_durations(case_head, hold, policy)
    print(
        f"  dt_spearman={timing.train_metrics.get('fit_spearman'):.3f} "
        f"case_head_fit={case_head.train_metrics.get('fit_spearman'):.3f}"
    )

    graph = build_org_from_policy(fit, policy, donor_id=cfg.donor_id)
    dof = degrees_of_freedom_report(graph)

    # baseline fit workload для выбора жертв стресса
    base_work = {a: auto.event_count for a, auto in graph.automata.items()}

    runs = {}
    for label, calibrate, stress_n in [
        ("baseline_raw", False, 0),
        ("calibrated", True, 0),
        ("stress_top3_calibrated", True, 3),
    ]:
        print(f"Симуляция [{label}]…")
        pol = policy
        disabled = []
        if stress_n:
            disabled = top_agents_by_workload(base_work, stress_n)
            pol = disable_agents(policy, set(disabled))
            decisions.append(f"Стресс {label}: disabled={disabled}")
        t_s = time.perf_counter()
        sim = simulate_batch(
            hold,
            pol,
            timing=timing,
            cfg=cfg,
            max_steps_per_case=40,
            seed=cfg.sim.seed,
            target_durations=targets if calibrate else None,
            calibrate_duration=calibrate,
        )
        elapsed = time.perf_counter() - t_s
        report = evaluate(hold, sim, policy=policy)
        # case-head spearman всегда считаем к targets
        actual_dur = actual_case_durations(hold)
        common = [c for c in sim.case_durations_sec if c in actual_dur]
        ad = np.array([actual_dur[c] for c in common], float)
        pd_ = np.array([sim.case_durations_sec[c] for c in common], float)
        emerg_sp = float(pd.Series(ad).corr(pd.Series(pd_), method="spearman")) if common else float("nan")
        report.metrics["sim_case_duration_spearman"] = emerg_sp
        report.metrics["sim_wall_sec"] = elapsed
        report.metrics["disabled_agents"] = disabled
        runs[label] = {"metrics": report.metrics, "sim_meta": sim.meta, "wall_sec": elapsed}
        print(
            f"  wall={elapsed:.1f}s events={len(sim.events)} "
            f"next_acc={report.metrics.get('holdout_next_step_accuracy'):.3f} "
            f"dur_sp={emerg_sp:.3f} weekly_corr={report.metrics.get('weekly_events_corr')}"
        )

    # критерии
    cal = runs["calibrated"]["metrics"]
    if (cal.get("sim_case_duration_spearman") or 0) < 0.2:
        failures.append(
            {
                "id": "CALIBRATED_DURATION_STILL_WEAK",
                "severity": "failure",
                "detail": f"После калибровки Spearman={cal.get('sim_case_duration_spearman')}",
            }
        )
    else:
        decisions.append(
            f"Калибровка подняла duration Spearman до {cal.get('sim_case_duration_spearman'):.3f} "
            "(не эмерджентность — зафиксировано)"
        )

    if runs["baseline_raw"]["wall_sec"] > 120:
        failures.append(
            {
                "id": "SIM_STILL_SLOW",
                "severity": "warning",
                "detail": f"baseline_raw wall={runs['baseline_raw']['wall_sec']:.1f}s",
            }
        )
    else:
        decisions.append(f"Батч-сима baseline_raw wall={runs['baseline_raw']['wall_sec']:.1f}s")

    # стресс: ожидание — меньше событий или выше hit_max / сдвиг workload
    stress = runs["stress_top3_calibrated"]
    base = runs["calibrated"]
    stress_delta = {
        "sim_events_delta": stress["metrics"]["sim_events"] - base["metrics"]["sim_events"],
        "weekly_corr_stress": stress["metrics"].get("weekly_events_corr"),
        "dur_spearman_stress": stress["metrics"].get("sim_case_duration_spearman"),
        "hit_max_stress": stress["sim_meta"].get("n_hit_max_steps"),
        "hit_max_base": base["sim_meta"].get("n_hit_max_steps"),
    }
    decisions.append(f"Стресс delta: {stress_delta}")

    payload = {
        "version": VER,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict(),
        "split_meta": split_meta,
        "train_policy": policy.train_metrics,
        "train_timing": timing.train_metrics,
        "train_case_duration": case_head.train_metrics,
        "prune": prune_info,
        "dof": dof,
        "runs": runs,
        "stress_delta": stress_delta,
        "decisions": decisions,
        "failures": failures,
    }

    (reports / f"run_v{VER}_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (reports / f"holdout_metrics_v{VER}.json").write_text(
        json.dumps(runs["calibrated"]["metrics"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / f"failures_v{VER}.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / f"experiment_config_v{VER}.json").write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = render_md(payload)
    (reports / f"run_v{VER}.md").write_text(md, encoding="utf-8")
    append_journal(reports / "LAB_JOURNAL.md", payload)
    print(md)
    print(f"\nГотово → reports/run_v{VER}.md")


def render_md(payload: dict) -> str:
    runs = payload["runs"]
    return f"""# OrgTwin v{payload['version']}

## Суть релиза
- Батч-encode softmax/timing в симуляции
- Калибровка длительности кейса под case-head (явный костыль)
- Стресс: выключение топ-3 агентов по fit-нагрузке
- Версионирование semver; артефакты только `*v{payload['version']}*`

## Результаты прогонов
```json
{json.dumps({k: {'wall_sec': v['wall_sec'], 'next_acc': v['metrics'].get('holdout_next_step_accuracy'), 'top3': v['metrics'].get('holdout_next_step_top3'), 'weekly_corr': v['metrics'].get('weekly_events_corr'), 'dur_spearman': v['metrics'].get('sim_case_duration_spearman'), 'sim_events': v['metrics'].get('sim_events'), 'hit_max': v['sim_meta'].get('n_hit_max_steps')} for k,v in runs.items()}, ensure_ascii=False, indent=2)}
```

## Stress delta
```json
{json.dumps(payload['stress_delta'], ensure_ascii=False, indent=2)}
```

## Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

## Неудачи / риски
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures'])}
"""


def append_journal(path: Path, payload: dict) -> None:
    block = f"""

---

## v{payload['version']} — OrgTwin ({payload['timestamp_utc']})

### Изменения
- Пакет/бренд: **OrgTwin** (`orgtwin`), semver в VERSION/pyproject/CHANGELOG
- Батч-сима; калибровка dt→case-head; stress top-3

### Метрики (кратко)
{json.dumps({k: {'wall_sec': v['wall_sec'], 'next_acc': v['metrics'].get('holdout_next_step_accuracy'), 'dur_sp': v['metrics'].get('sim_case_duration_spearman'), 'weekly': v['metrics'].get('weekly_events_corr')} for k,v in payload['runs'].items()}, ensure_ascii=False, indent=2)}

### Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

### Неудачи
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures'])}

### Артефакты
- `reports/run_v{payload['version']}.md`, `run_v{payload['version']}_full.json`
"""
    with path.open("a", encoding="utf-8") as f:
        f.write(block)


if __name__ == "__main__":
    main()
