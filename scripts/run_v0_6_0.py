#!/usr/bin/env python3
"""
OrgTwin v0.6.0 — полноценный FEP (agent-level + тюнинг на fit) vs Softmax.

Исправления паритета относительно 0.5.0:
  habit на agent; backoff; C(o|ctx); подбор гиперпараметров только на fit.

Руки:
  softmax | fep_habit_only (лучший по fit) | fep_full_efe (лучший full по fit)
+ ссылка на метрики кривого 0.5.0 из reports (не пересчёт).
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
from orgtwin.policy.fep import (
    FEPConfig,
    default_fep_tune_grid,
    next_step_accuracy_fep,
    train_fep_policies,
    tune_fep_on_fit,
)
from orgtwin.policy.softmax import prune_membrane_actions, train_softmax_policies
from orgtwin.policy.timing import (
    predict_case_durations,
    train_case_duration_model,
    train_timing_model,
)
from orgtwin.sim.engine import simulate_batch

VER = "0.6.0"
assert __version__ == VER, f"VERSION mismatch package={__version__} script={VER}"


def _sim_arm(name, hold, policy, timing, case_head, cfg):
    targets = predict_case_durations(case_head, hold, policy)
    t0 = time.perf_counter()
    sim = simulate_batch(
        hold,
        policy,
        timing=timing,
        cfg=cfg,
        max_steps_per_case=cfg.sim.max_steps_per_case,
        seed=cfg.sim.seed,
        calibrate_duration=False,
    )
    wall = time.perf_counter() - t0
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
    # cal справка
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
    report_cal = evaluate(hold, sim_cal, policy=policy)
    if common:
        pd_c = np.array(
            [sim_cal.case_durations_sec[c] for c in common if c in sim_cal.case_durations_sec], float
        )
        ad_c = np.array(
            [actual_dur[c] for c in common if c in sim_cal.case_durations_sec], float
        )
        cal_sp = (
            float(pd.Series(ad_c).corr(pd.Series(pd_c), method="spearman")) if len(ad_c) else float("nan")
        )
    else:
        cal_sp = float("nan")
    return {
        "label": name,
        "policy_kind": getattr(policy, "policy_kind", "softmax"),
        "wall_sec": wall,
        "metrics_raw": report.metrics,
        "metrics_cal": {**report_cal.metrics, "sim_case_duration_spearman": cal_sp},
        "sim_meta": sim.meta,
        "train_metrics": dict(policy.train_metrics),
        "fep_cfg": getattr(getattr(policy, "fep_cfg", None), "__dict__", None),
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
        f"Релиз OrgTwin {VER}: FEP с agent-level habit + тюнинг на fit vs Softmax",
        "Holdout не используется для выбора гиперпараметров FEP",
        "0.5.0 FEP (role-level) сохранён в reports/run_v0.5.0.* как кривой baseline",
    ]

    print(f"OrgTwin {VER}")
    print("Загрузка XES…")
    t0 = time.perf_counter()
    df = load_event_table(xes)
    print(f"  событий={len(df)} ({time.perf_counter()-t0:.1f}s)")

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
    print(f"  fit_acc={softmax_pol.train_metrics['fit_action_accuracy']:.3f} ({time.perf_counter()-t1:.1f}s)")

    print("Обучение FEP (счётчики + тюнинг на fit)…")
    t2 = time.perf_counter()
    fep_base = train_fep_policies(
        fit,
        fep_cfg=FEPConfig(mode="habit_only", gamma_precision=4.0),
        amount_bin_edges=softmax_pol.amount_bin_edges,
        tune=False,
    )
    grid = default_fep_tune_grid()
    # раздельно: лучший habit_only и лучший full_efe
    habit_grid = [c for c in grid if c.mode == "habit_only"]
    full_grid = [c for c in grid if c.mode == "full_efe"]
    fep_habit, habit_rows = tune_fep_on_fit(
        fep_base, fit, habit_grid, eval_max_rows=cfg.fep.tune_eval_max_rows
    )
    fep_full, full_rows = tune_fep_on_fit(
        fep_base, fit, full_grid, eval_max_rows=cfg.fep.tune_eval_max_rows
    )
    # финальные метрики fit на полном subsample
    for pol, tag in ((fep_habit, "habit"), (fep_full, "full")):
        ns = next_step_accuracy_fep(pol, fit, with_efe_components=True, max_rows=40000)
        pol.train_metrics.update(
            {
                "fit_action_accuracy": ns["accuracy"],
                "fit_top3_accuracy": ns["top3_accuracy"],
                "generative_cross_entropy": ns["cross_entropy"],
                "mean_G_truth": ns.get("mean_G_truth"),
                "mean_risk": ns.get("mean_risk"),
                "mean_ambiguity": ns.get("mean_ambiguity"),
                "mean_habit_term": ns.get("mean_habit"),
            }
        )
        print(
            f"  FEP-{tag}: mode={pol.fep_cfg.mode} γ={pol.fep_cfg.gamma_precision} "
            f"w=({pol.fep_cfg.risk_weight},{pol.fep_cfg.ambiguity_weight},{pol.fep_cfg.habit_weight}) "
            f"fit_acc={ns['accuracy']:.3f}"
        )
    decisions.append(f"FEP habit selected: {fep_habit.train_metrics.get('tune_selected')}")
    decisions.append(f"FEP full selected: {fep_full.train_metrics.get('tune_selected')}")
    print(f"  FEP train+tune wall={time.perf_counter()-t2:.1f}s")

    timing = train_timing_model(fit, softmax_pol, cfg=cfg.timing)
    case_head = train_case_duration_model(fit, softmax_pol, cfg=cfg.timing)
    print(f"  timing dt_spearman={timing.train_metrics.get('fit_spearman'):.3f}")

    arms = {}
    for name, pol in [
        ("softmax", softmax_pol),
        ("fep_habit_only", fep_habit),
        ("fep_full_efe", fep_full),
    ]:
        print(f"Симуляция [{name}]…")
        arms[name] = _sim_arm(name, hold, pol, timing, case_head, cfg)
        m = arms[name]["metrics_raw"]
        print(
            f"  next_acc={m.get('holdout_next_step_accuracy'):.3f} "
            f"top3={m.get('holdout_next_step_top3'):.3f} "
            f"weekly={m.get('weekly_events_corr')} "
            f"wall={arms[name]['wall_sec']:.1f}s"
        )

    # кривой 0.5.0 из артефакта
    crooked = None
    p05 = reports / "holdout_metrics_v0.5.0.json"
    if p05.exists():
        crooked = json.loads(p05.read_text(encoding="utf-8"))
        decisions.append("В отчёт включены метрики FEP 0.5.0 (role-level) из артефакта")

    def _m(arm, key):
        return arms[arm]["metrics_raw"].get(key)

    comparison = {
        "next_step_accuracy": {
            "softmax": _m("softmax", "holdout_next_step_accuracy"),
            "fep_habit_only": _m("fep_habit_only", "holdout_next_step_accuracy"),
            "fep_full_efe": _m("fep_full_efe", "holdout_next_step_accuracy"),
            "fep_0_5_0_crooked": (crooked or {})
            .get("arms_raw", {})
            .get("fep_efe", {})
            .get("holdout_next_step_accuracy"),
        },
        "top3_accuracy": {
            "softmax": _m("softmax", "holdout_next_step_top3"),
            "fep_habit_only": _m("fep_habit_only", "holdout_next_step_top3"),
            "fep_full_efe": _m("fep_full_efe", "holdout_next_step_top3"),
            "fep_0_5_0_crooked": (crooked or {})
            .get("arms_raw", {})
            .get("fep_efe", {})
            .get("holdout_next_step_top3"),
        },
        "weekly_events_corr": {
            "softmax": _m("softmax", "weekly_events_corr"),
            "fep_habit_only": _m("fep_habit_only", "weekly_events_corr"),
            "fep_full_efe": _m("fep_full_efe", "weekly_events_corr"),
            "fep_0_5_0_crooked": (crooked or {})
            .get("arms_raw", {})
            .get("fep_efe", {})
            .get("weekly_events_corr"),
        },
        "cross_entropy": {
            "softmax": _m("softmax", "holdout_next_step_ce"),
            "fep_habit_only": _m("fep_habit_only", "holdout_next_step_ce"),
            "fep_full_efe": _m("fep_full_efe", "holdout_next_step_ce"),
        },
        "sim_wall_sec": {k: v["wall_sec"] for k, v in arms.items()},
        "delta_habit_minus_softmax_next": (_m("fep_habit_only", "holdout_next_step_accuracy") or 0)
        - (_m("softmax", "holdout_next_step_accuracy") or 0),
        "delta_full_minus_softmax_next": (_m("fep_full_efe", "holdout_next_step_accuracy") or 0)
        - (_m("softmax", "holdout_next_step_accuracy") or 0),
        "delta_habit_minus_crooked_0_5_next": (
            (_m("fep_habit_only", "holdout_next_step_accuracy") or 0)
            - (
                (crooked or {}).get("arms_raw", {}).get("fep_efe", {}).get("holdout_next_step_accuracy")
                or 0
            )
        ),
    }

    # победители
    scores = {
        "softmax": _m("softmax", "holdout_next_step_accuracy") or -1,
        "fep_habit_only": _m("fep_habit_only", "holdout_next_step_accuracy") or -1,
        "fep_full_efe": _m("fep_full_efe", "holdout_next_step_accuracy") or -1,
    }
    winner_ns = max(scores, key=scores.get)
    w_scores = {
        "softmax": _m("softmax", "weekly_events_corr") or -1,
        "fep_habit_only": _m("fep_habit_only", "weekly_events_corr") or -1,
        "fep_full_efe": _m("fep_full_efe", "weekly_events_corr") or -1,
    }
    winner_weekly = max(w_scores, key=w_scores.get)
    decisions.append(f"Победитель next-step: {winner_ns}")
    decisions.append(f"Победитель weekly_corr: {winner_weekly}")

    if abs(comparison["delta_habit_minus_softmax_next"]) < 0.02:
        decisions.append(
            f"FEP habit_only близок к softmax по next-step (Δ={comparison['delta_habit_minus_softmax_next']:+.4f})"
        )

    payload = {
        "version": VER,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict(),
        "split_meta": split_meta,
        "prune_softmax": prune_info,
        "tune_habit_grid": habit_rows,
        "tune_full_grid": full_rows,
        "arms": {
            k: {
                "policy_kind": v["policy_kind"],
                "wall_sec": v["wall_sec"],
                "fep_cfg": v["fep_cfg"],
                "train_metrics": {
                    kk: vv
                    for kk, vv in v["train_metrics"].items()
                    if kk not in ("tune_grid",)  # сетка отдельно
                },
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

    def fmt(x):
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.4f}"
        return str(x)

    return f"""# OrgTwin v{payload['version']}

## Суть (RU)
Исправление FEP до паритета с softmax по контексту агента + тюнинг на fit.
Руки: softmax | fep_habit_only | fep_full_efe; кривой FEP 0.5.0 — из артефакта.

## 说明 (中文)
修正 FEP：智能体级 habit + 仅在 fit 上调参。对比 softmax / habit_only / full_efe；0.5.0 扭曲 FEP 来自既有产物。

## Holdout (raw)
| Метрика | Softmax | FEP habit | FEP full EFE | FEP 0.5.0 (кривой) |
|---------|---------|-----------|--------------|---------------------|
| next-step | {fmt(c['next_step_accuracy']['softmax'])} | {fmt(c['next_step_accuracy']['fep_habit_only'])} | {fmt(c['next_step_accuracy']['fep_full_efe'])} | {fmt(c['next_step_accuracy']['fep_0_5_0_crooked'])} |
| top-3 | {fmt(c['top3_accuracy']['softmax'])} | {fmt(c['top3_accuracy']['fep_habit_only'])} | {fmt(c['top3_accuracy']['fep_full_efe'])} | {fmt(c['top3_accuracy']['fep_0_5_0_crooked'])} |
| weekly_corr | {fmt(c['weekly_events_corr']['softmax'])} | {fmt(c['weekly_events_corr']['fep_habit_only'])} | {fmt(c['weekly_events_corr']['fep_full_efe'])} | {fmt(c['weekly_events_corr']['fep_0_5_0_crooked'])} |

Δ habit−softmax next: {c['delta_habit_minus_softmax_next']:+.4f}  
Δ full−softmax next: {c['delta_full_minus_softmax_next']:+.4f}  
Δ habit−0.5.0 next: {c['delta_habit_minus_crooked_0_5_next']:+.4f}

Победитель next-step: **{payload['winner_next_step']}**; weekly: **{payload['winner_weekly']}**.

## Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

## Неудачи / риски
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures'])}
"""


def append_journal(path: Path, payload: dict) -> None:
    c = payload["comparison"]
    block = f"""

---

## v{payload['version']} — FEP parity vs Softmax ({payload['timestamp_utc']})

### Изменения
- FEP: habit (prev,amount_bin,**agent**) + backoff; C(o|ctx); тюнинг на fit
- Руки: softmax, fep_habit_only, fep_full_efe; сравнение с 0.5.0 crooked

### Holdout next-step
- SM={c['next_step_accuracy']['softmax']} habit={c['next_step_accuracy']['fep_habit_only']} full={c['next_step_accuracy']['fep_full_efe']} crooked05={c['next_step_accuracy']['fep_0_5_0_crooked']}
- winner={payload['winner_next_step']}; weekly_winner={payload['winner_weekly']}

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
