#!/usr/bin/env python3
"""
OrgTwin v0.5.0 — FEP / минимизация ожидаемой свободной энергии vs softmax.

Один split, один timing, две политики:
  A) Softmax (мультиномиальная логистика) — baseline 0.4
  B) FEP/EFE (Dirichlet + Risk+Ambiguity−Habit, π∝exp(−γG)) — Friston

Артефакты только *v0.5.0*; старые reports не трогаем.
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
from orgtwin.eval.score import actual_case_durations, evaluate
from orgtwin.ingest.xes_loader import fit_holdout_split, load_event_table
from orgtwin.policy.fep import FEPConfig, train_fep_policies
from orgtwin.policy.softmax import prune_membrane_actions, train_softmax_policies
from orgtwin.policy.timing import (
    predict_case_durations,
    train_case_duration_model,
    train_timing_model,
)
from orgtwin.sim.engine import simulate_batch

VER = "0.5.0"
assert __version__ == VER, f"VERSION mismatch package={__version__} script={VER}"


def _run_sim_eval(label: str, hold, policy, timing, case_head, cfg, decisions, failures):
    targets = predict_case_durations(case_head, hold, policy)
    t_s = time.perf_counter()
    sim = simulate_batch(
        hold,
        policy,
        timing=timing,
        cfg=cfg,
        max_steps_per_case=cfg.sim.max_steps_per_case,
        seed=cfg.sim.seed,
        target_durations=None,
        calibrate_duration=False,
    )
    wall = time.perf_counter() - t_s
    report = evaluate(hold, sim, policy=policy)
    actual_dur = actual_case_durations(hold)
    common = [c for c in sim.case_durations_sec if c in actual_dur]
    if common:
        ad = np.array([actual_dur[c] for c in common], float)
        pd_ = np.array([sim.case_durations_sec[c] for c in common], float)
        emerg_sp = float(pd.Series(ad).corr(pd.Series(pd_), method="spearman"))
    else:
        emerg_sp = float("nan")
    report.metrics["sim_case_duration_spearman"] = emerg_sp
    report.metrics["sim_wall_sec"] = wall
    # калиброванный прогон (для fair duration compare)
    t_c = time.perf_counter()
    sim_cal = simulate_batch(
        hold,
        policy,
        timing=timing,
        cfg=cfg,
        max_steps_per_case=cfg.sim.max_steps_per_case,
        seed=cfg.sim.seed,
        target_durations=targets,
        calibrate_duration=True,
    )
    wall_cal = time.perf_counter() - t_c
    report_cal = evaluate(hold, sim_cal, policy=policy)
    if common:
        pd_c = np.array([sim_cal.case_durations_sec[c] for c in common if c in sim_cal.case_durations_sec], float)
        ad_c = np.array([actual_dur[c] for c in common if c in sim_cal.case_durations_sec], float)
        cal_sp = float(pd.Series(ad_c).corr(pd.Series(pd_c), method="spearman")) if len(ad_c) else float("nan")
    else:
        cal_sp = float("nan")
    return {
        "label": label,
        "wall_sec": wall,
        "wall_cal_sec": wall_cal,
        "metrics_raw": report.metrics,
        "metrics_cal": {**report_cal.metrics, "sim_case_duration_spearman": cal_sp},
        "sim_meta": sim.meta,
        "sim_meta_cal": sim_cal.meta,
        "train_metrics": dict(policy.train_metrics),
        "policy_kind": getattr(policy, "policy_kind", "softmax"),
    }


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
        f"Релиз OrgTwin {VER}: A/B Softmax vs FEP (EFE Friston)",
        "Один split 3+2, один seed; timing обучается на softmax-бандле edges, FEP шарит edges",
        "Калибровка длительности — для справки; сравнение политик по raw next-step и weekly",
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

    # --- Softmax ---
    print("Обучение softmax…")
    t1 = time.perf_counter()
    softmax_pol = train_softmax_policies(
        fit,
        lambda_entropy=cfg.policy.lambda_entropy,
        max_iter=cfg.policy.max_iter,
        random_state=cfg.policy.random_state,
        solver=cfg.policy.solver,
        tol=cfg.policy.tol,
        C=cfg.policy.C,
    )
    prune_info = prune_membrane_actions(
        softmax_pol, fit, lambda_entropy=cfg.policy.lambda_entropy, min_support=cfg.policy.prune_min_support
    )
    restored = []
    for role, acts in list(prune_info.get("pruned_actions_by_role", {}).items()):
        for a in acts:
            if "DECLINED" in a and a in softmax_pol.action_classes:
                idx = softmax_pol.action_classes.index(a)
                softmax_pol.role_action_mask[role][idx] = True
                restored.append(f"{role}:{a}")
    if restored:
        decisions.append(f"Softmax: откат прунинга DECLINED: {restored}")
    print(
        f"  fit_acc={softmax_pol.train_metrics['fit_action_accuracy']:.3f} "
        f"F_proxy={softmax_pol.train_metrics['free_energy_proxy']:.3f} ({time.perf_counter()-t1:.1f}s)"
    )

    # --- FEP (те же amount edges) ---
    print("Обучение FEP/EFE…")
    t2 = time.perf_counter()
    fep_cfg = FEPConfig(
        dirichlet_alpha=cfg.fep.dirichlet_alpha,
        gamma_precision=2.0,  # как в зафиксированном прогоне 0.5.0
        preference_power=cfg.fep.preference_power,
        habit_weight=1.0,
        ambiguity_weight=1.0,
        risk_weight=1.0,
        empty_transition_entropy=3.0,
        mode="full_efe",  # 0.5.0 был full EFE с равными весами (role-level habit — в коде ≥0.6 уже agent-level)
    )
    fep_pol = train_fep_policies(
        fit, fep_cfg=fep_cfg, amount_bin_edges=softmax_pol.amount_bin_edges
    )
    print(
        f"  fit_acc={fep_pol.train_metrics['fit_action_accuracy']:.3f} "
        f"FE={fep_pol.train_metrics['variational_free_energy_nats']:.3f} "
        f"mean_G={fep_pol.train_metrics['mean_G_truth']:.3f} ({time.perf_counter()-t2:.1f}s)"
    )
    decisions.append(
        f"FEP cfg: α={fep_cfg.dirichlet_alpha} γ={fep_cfg.gamma_precision} "
        f"w_r/a/h={fep_cfg.risk_weight}/{fep_cfg.ambiguity_weight}/{fep_cfg.habit_weight}"
    )

    # timing на softmax (тот же Ridge); FEP использует тот же timing + свои latency fallback
    timing = train_timing_model(fit, softmax_pol, cfg=cfg.timing)
    case_head = train_case_duration_model(fit, softmax_pol, cfg=cfg.timing)
    print(f"  timing dt_spearman={timing.train_metrics.get('fit_spearman'):.3f}")

    arms = {}
    for name, pol in [("softmax", softmax_pol), ("fep_efe", fep_pol)]:
        print(f"Симуляция [{name}]…")
        arms[name] = _run_sim_eval(name, hold, pol, timing, case_head, cfg, decisions, failures)
        m = arms[name]["metrics_raw"]
        print(
            f"  next_acc={m.get('holdout_next_step_accuracy'):.3f} "
            f"top3={m.get('holdout_next_step_top3'):.3f} "
            f"weekly={m.get('weekly_events_corr')} "
            f"dur_sp={m.get('sim_case_duration_spearman'):.3f} "
            f"wall={arms[name]['wall_sec']:.1f}s"
        )

    # сравнение
    s, f = arms["softmax"]["metrics_raw"], arms["fep_efe"]["metrics_raw"]
    comparison = {
        "next_step_accuracy": {
            "softmax": s.get("holdout_next_step_accuracy"),
            "fep_efe": f.get("holdout_next_step_accuracy"),
            "delta_fep_minus_softmax": (f.get("holdout_next_step_accuracy") or 0)
            - (s.get("holdout_next_step_accuracy") or 0),
        },
        "top3_accuracy": {
            "softmax": s.get("holdout_next_step_top3"),
            "fep_efe": f.get("holdout_next_step_top3"),
            "delta_fep_minus_softmax": (f.get("holdout_next_step_top3") or 0)
            - (s.get("holdout_next_step_top3") or 0),
        },
        "cross_entropy": {
            "softmax": s.get("holdout_next_step_ce"),
            "fep_efe": f.get("holdout_next_step_ce"),
            "delta_fep_minus_softmax": (f.get("holdout_next_step_ce") or 0)
            - (s.get("holdout_next_step_ce") or 0),
        },
        "weekly_events_corr": {
            "softmax": s.get("weekly_events_corr"),
            "fep_efe": f.get("weekly_events_corr"),
            "delta_fep_minus_softmax": (f.get("weekly_events_corr") or 0)
            - (s.get("weekly_events_corr") or 0),
        },
        "sim_duration_spearman_raw": {
            "softmax": s.get("sim_case_duration_spearman"),
            "fep_efe": f.get("sim_case_duration_spearman"),
        },
        "sim_duration_spearman_cal": {
            "softmax": arms["softmax"]["metrics_cal"].get("sim_case_duration_spearman"),
            "fep_efe": arms["fep_efe"]["metrics_cal"].get("sim_case_duration_spearman"),
        },
        "sim_wall_sec": {
            "softmax": arms["softmax"]["wall_sec"],
            "fep_efe": arms["fep_efe"]["wall_sec"],
        },
        "free_energy_metric": {
            "softmax_proxy_CE_plus_lamH": s.get("holdout_free_energy_proxy"),
            "fep_variational_FE_gen_CE": f.get("holdout_variational_FE"),
            "fep_mean_G_truth": f.get("holdout_mean_G_truth"),
            "note": "Метрики FE несопоставимы 1:1: у softmax — CE+λH прокси; у FEP — generative CE / EFE",
        },
    }

    # вердикт по holdout next-step и weekly
    winner_ns = (
        "fep_efe"
        if (f.get("holdout_next_step_accuracy") or 0) > (s.get("holdout_next_step_accuracy") or 0)
        else "softmax"
        if (f.get("holdout_next_step_accuracy") or 0) < (s.get("holdout_next_step_accuracy") or 0)
        else "tie"
    )
    winner_weekly = (
        "fep_efe"
        if (f.get("weekly_events_corr") or -1) > (s.get("weekly_events_corr") or -1)
        else "softmax"
        if (f.get("weekly_events_corr") or -1) < (s.get("weekly_events_corr") or -1)
        else "tie"
    )
    decisions.append(f"Победитель next-step accuracy: {winner_ns}")
    decisions.append(f"Победитель weekly_corr: {winner_weekly}")

    if abs(comparison["next_step_accuracy"]["delta_fep_minus_softmax"]) < 0.01:
        failures.append(
            {
                "id": "FEP_SOFTMAX_NEAR_TIE_NEXT_STEP",
                "severity": "observation",
                "detail": f"Δacc={comparison['next_step_accuracy']['delta_fep_minus_softmax']:.4f}",
            }
        )

    if (f.get("holdout_next_step_accuracy") or 0) < 0.3:
        failures.append(
            {
                "id": "FEP_NEXT_STEP_WEAK",
                "severity": "failure",
                "detail": f"fep next_acc={f.get('holdout_next_step_accuracy')}",
            }
        )

    payload = {
        "version": VER,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict(),
        "split_meta": split_meta,
        "prune_softmax": prune_info,
        "arms": {
            k: {
                "policy_kind": v["policy_kind"],
                "wall_sec": v["wall_sec"],
                "wall_cal_sec": v["wall_cal_sec"],
                "train_metrics": v["train_metrics"],
                "metrics_raw": v["metrics_raw"],
                "metrics_cal": v["metrics_cal"],
                "sim_meta": v["sim_meta"],
            }
            for k, v in arms.items()
        },
        "comparison": comparison,
        "winner_next_step": winner_ns,
        "winner_weekly": winner_weekly,
        "decisions": decisions,
        "failures": failures,
    }

    (reports / f"run_v{VER}_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (reports / f"holdout_metrics_v{VER}.json").write_text(
        json.dumps(
            {"comparison": comparison, "arms_raw": {k: v["metrics_raw"] for k, v in arms.items()}},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
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
    c = payload["comparison"]
    return f"""# OrgTwin v{payload['version']}

## Суть релиза
A/B на одном доноре BPIC2012 / одном split:
- **softmax** — мультиномиальная логистика P(Action|Information, agent)
- **fep_efe** — активный вывод Friston: G = Risk + Ambiguity − Habit, π∝exp(−γG)

## Сравнение (holdout, raw sim)
| Метрика | Softmax | FEP/EFE | Δ (FEP−SM) |
|---------|---------|---------|------------|
| next-step acc | {c['next_step_accuracy']['softmax']:.4f} | {c['next_step_accuracy']['fep_efe']:.4f} | {c['next_step_accuracy']['delta_fep_minus_softmax']:+.4f} |
| top-3 | {c['top3_accuracy']['softmax']:.4f} | {c['top3_accuracy']['fep_efe']:.4f} | {c['top3_accuracy']['delta_fep_minus_softmax']:+.4f} |
| CE (nats) | {c['cross_entropy']['softmax']:.4f} | {c['cross_entropy']['fep_efe']:.4f} | {c['cross_entropy']['delta_fep_minus_softmax']:+.4f} |
| weekly_corr | {c['weekly_events_corr']['softmax']} | {c['weekly_events_corr']['fep_efe']} | {c['weekly_events_corr']['delta_fep_minus_softmax']} |
| dur Spearman raw | {c['sim_duration_spearman_raw']['softmax']} | {c['sim_duration_spearman_raw']['fep_efe']} | — |
| wall sec | {c['sim_wall_sec']['softmax']:.1f} | {c['sim_wall_sec']['fep_efe']:.1f} | — |

Победитель next-step: **{payload['winner_next_step']}**; weekly: **{payload['winner_weekly']}**.

## Свободная энергия
```json
{json.dumps(c['free_energy_metric'], ensure_ascii=False, indent=2)}
```

## Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

## Неудачи / риски
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures'])}
"""


def append_journal(path: Path, payload: dict) -> None:
    c = payload["comparison"]
    block = f"""

---

## v{payload['version']} — FEP vs Softmax ({payload['timestamp_utc']})

### Изменения
- Политика активного вывода: Dirichlet + EFE (Risk+Ambiguity−Habit), π∝exp(−γG)
- A/B с softmax на одном split; артефакты `*v{payload['version']}*`

### Сравнение (кратко)
- next_acc: SM={c['next_step_accuracy']['softmax']:.4f} FEP={c['next_step_accuracy']['fep_efe']:.4f} (winner={payload['winner_next_step']})
- weekly: SM={c['weekly_events_corr']['softmax']} FEP={c['weekly_events_corr']['fep_efe']} (winner={payload['winner_weekly']})
- top3: SM={c['top3_accuracy']['softmax']:.4f} FEP={c['top3_accuracy']['fep_efe']:.4f}

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
