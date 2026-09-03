"""
Единый прогон эксперимента OrgTwin из JSON-конфига.

Различие версий — в configs/experiments/vX.Y.Z.json, не в копиях scripts/run_*.py.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from orgtwin.config.constants import (
    EvalConfig,
    ExperimentConfig,
    FEPPolicyConfig,
    PolicyConfig,
    SimConfig,
    SplitConfig,
    TimingConfig,
)
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


def _cfg_from_dict(d: dict) -> ExperimentConfig:
    exp = d.get("experiment", d)
    return ExperimentConfig(
        donor_id=exp.get("donor_id", "BPIC2012"),
        donor_doi=exp.get("donor_doi", ""),
        split=SplitConfig(**{k: v for k, v in exp.get("split", {}).items() if k in SplitConfig.__dataclass_fields__}),
        policy=PolicyConfig(
            **{
                k: (tuple(v) if k in ("amount_quantiles", "terminal_prefixes") and isinstance(v, list) else v)
                for k, v in exp.get("policy", {}).items()
                if k in PolicyConfig.__dataclass_fields__
            }
        ),
        fep=FEPPolicyConfig(**{k: v for k, v in exp.get("fep", {}).items() if k in FEPPolicyConfig.__dataclass_fields__}),
        timing=TimingConfig(**{k: v for k, v in exp.get("timing", {}).items() if k in TimingConfig.__dataclass_fields__}),
        sim=SimConfig(**{k: v for k, v in exp.get("sim", {}).items() if k in SimConfig.__dataclass_fields__}),
        eval=EvalConfig(**{k: v for k, v in exp.get("eval", {}).items() if k in EvalConfig.__dataclass_fields__}),
    )


def _sim_arm(name: str, hold, policy, timing, case_head, cfg: ExperimentConfig) -> dict:
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
        ad_c = np.array([actual_dur[c] for c in common if c in sim_cal.case_durations_sec], float)
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


def run_softmax_fep_ab(root: Path, recipe: dict, package_version: str) -> dict:
    """Рецепт: Softmax vs FEP habit_only vs FEP full_efe (как 0.6.0)."""
    ver = str(recipe["version"])
    cfg = _cfg_from_dict(recipe)
    xes = root / recipe["donor"]["xes_path"]
    derived = root / "data" / "derived"
    reports = root / "reports"
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    decisions: list[str] = list(recipe.get("decisions_seed", []))
    decisions.append(f"Прогон через scripts/run_experiment.py --config (версия {ver})")
    decisions.append(f"package_version={package_version}")

    print(f"OrgTwin experiment {ver} (package {package_version})")
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
        softmax_pol,
        fit,
        lambda_entropy=cfg.policy.lambda_entropy,
        min_support=cfg.policy.prune_min_support,
    )
    restored = []
    if recipe.get("rollback_declined_prune", True):
        for role, acts in list(prune_info.get("pruned_actions_by_role", {}).items()):
            for a in acts:
                if "DECLINED" in a and a in softmax_pol.action_classes:
                    idx = softmax_pol.action_classes.index(a)
                    softmax_pol.role_action_mask[role][idx] = True
                    restored.append(f"{role}:{a}")
        if restored:
            decisions.append(f"Softmax: откат прунинга DECLINED: {restored}")
    print(f"  fit_acc={softmax_pol.train_metrics['fit_action_accuracy']:.3f} ({time.perf_counter()-t1:.1f}s)")

    print("Обучение FEP…")
    t2 = time.perf_counter()
    fep_base = train_fep_policies(
        fit,
        fep_cfg=FEPConfig(mode="habit_only", gamma_precision=cfg.fep.gamma_precision),
        amount_bin_edges=softmax_pol.amount_bin_edges,
        tune=False,
    )
    grid = default_fep_tune_grid()
    habit_grid = [c for c in grid if c.mode == "habit_only"]
    full_grid = [c for c in grid if c.mode == "full_efe"]
    fep_habit, habit_rows = tune_fep_on_fit(
        fep_base, fit, habit_grid, eval_max_rows=cfg.fep.tune_eval_max_rows
    )
    fep_full, full_rows = tune_fep_on_fit(
        fep_base, fit, full_grid, eval_max_rows=cfg.fep.tune_eval_max_rows
    )
    for pol, tag in ((fep_habit, "habit"), (fep_full, "full")):
        ns = next_step_accuracy_fep(pol, fit, with_efe_components=True, max_rows=40000)
        pol.train_metrics.update(
            {
                "fit_action_accuracy": ns["accuracy"],
                "fit_top3_accuracy": ns["top3_accuracy"],
                "generative_cross_entropy": ns["cross_entropy"],
                "mean_G_truth": ns.get("mean_G_truth"),
            }
        )
        print(
            f"  FEP-{tag}: γ={pol.fep_cfg.gamma_precision} "
            f"fit_acc={ns['accuracy']:.3f}"
        )
    decisions.append(f"FEP habit selected: {fep_habit.train_metrics.get('tune_selected')}")
    decisions.append(f"FEP full selected: {fep_full.train_metrics.get('tune_selected')}")
    print(f"  FEP train+tune wall={time.perf_counter()-t2:.1f}s")

    timing = train_timing_model(fit, softmax_pol, cfg=cfg.timing)
    case_head = train_case_duration_model(fit, softmax_pol, cfg=cfg.timing)

    arms_spec = recipe.get("arms", ["softmax", "fep_habit_only", "fep_full_efe"])
    policy_map = {
        "softmax": softmax_pol,
        "fep_habit_only": fep_habit,
        "fep_full_efe": fep_full,
    }
    arms: dict[str, Any] = {}
    for name in arms_spec:
        print(f"Симуляция [{name}]…")
        arms[name] = _sim_arm(name, hold, policy_map[name], timing, case_head, cfg)
        m = arms[name]["metrics_raw"]
        print(
            f"  next_acc={m.get('holdout_next_step_accuracy'):.3f} "
            f"weekly={m.get('weekly_events_corr')} "
            f"wall={arms[name]['wall_sec']:.1f}s"
        )

    crooked = None
    crooked_path = recipe.get("compare_crooked_fep_metrics")
    if crooked_path:
        p = root / crooked_path
        if p.exists():
            crooked = json.loads(p.read_text(encoding="utf-8"))
            decisions.append(f"Сравнение с артефактом: {crooked_path}")

    def _m(arm: str, key: str):
        return arms[arm]["metrics_raw"].get(key)

    comparison = {
        "next_step_accuracy": {k: _m(k, "holdout_next_step_accuracy") for k in arms},
        "top3_accuracy": {k: _m(k, "holdout_next_step_top3") for k in arms},
        "weekly_events_corr": {k: _m(k, "weekly_events_corr") for k in arms},
        "cross_entropy": {k: _m(k, "holdout_next_step_ce") for k in arms},
        "sim_wall_sec": {k: v["wall_sec"] for k, v in arms.items()},
    }
    if crooked:
        comparison["next_step_accuracy"]["fep_0_5_0_crooked"] = (
            crooked.get("arms_raw", {}).get("fep_efe", {}).get("holdout_next_step_accuracy")
        )
        comparison["weekly_events_corr"]["fep_0_5_0_crooked"] = (
            crooked.get("arms_raw", {}).get("fep_efe", {}).get("weekly_events_corr")
        )

    winner_ns = max(arms, key=lambda k: _m(k, "holdout_next_step_accuracy") or -1)
    winner_weekly = max(arms, key=lambda k: _m(k, "weekly_events_corr") or -1)
    decisions.append(f"Победитель next-step: {winner_ns}")
    decisions.append(f"Победитель weekly_corr: {winner_weekly}")

    payload = {
        "version": ver,
        "recipe": recipe.get("recipe", "softmax_fep_ab"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": recipe.get("_config_path"),
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
                "train_metrics": {kk: vv for kk, vv in v["train_metrics"].items() if kk != "tune_grid"},
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
        "notes_ru": recipe.get("notes_ru", ""),
        "notes_zh": recipe.get("notes_zh", ""),
    }

    (reports / f"run_v{ver}_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (reports / f"holdout_metrics_v{ver}.json").write_text(
        json.dumps(
            {"comparison": comparison, "arms_raw": {k: v["metrics_raw"] for k, v in arms.items()}},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (derived / f"failures_v{ver}.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / f"experiment_config_v{ver}.json").write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = _render_md(payload)
    (reports / f"run_v{ver}.md").write_text(md, encoding="utf-8")
    _append_journal(reports / "LAB_JOURNAL.md", payload)
    print(md)
    print(f"\nГотово → reports/run_v{ver}.md")
    return payload


def _render_md(payload: dict) -> str:
    c = payload["comparison"]
    arms = list(payload["arms"].keys())

    def fmt(x):
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.4f}"
        return str(x)

    header = "| Метрика | " + " | ".join(arms) + " |"
    sep = "|---------|" + "|".join(["------"] * len(arms)) + "|"
    rows = []
    for metric, key in (
        ("next-step", "next_step_accuracy"),
        ("top-3", "top3_accuracy"),
        ("weekly_corr", "weekly_events_corr"),
    ):
        rows.append(
            "| "
            + metric
            + " | "
            + " | ".join(fmt(c.get(key, {}).get(a)) for a in arms)
            + " |"
        )

    return f"""# OrgTwin v{payload['version']}

## Русский
{payload.get('notes_ru') or 'Прогон softmax_fep_ab через единый run_experiment.py.'}

Рецепт: `{payload.get('recipe')}`. Конфиг: `{payload.get('config_path')}`.

## 中文
{payload.get('notes_zh') or '通过统一 run_experiment.py 运行 softmax_fep_ab。'}

## Holdout (raw)
{header}
{sep}
{chr(10).join(rows)}

Победитель next-step: **{payload['winner_next_step']}**; weekly: **{payload['winner_weekly']}**.

## Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

## Неудачи / риски
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures'])}
"""


def _append_journal(path: Path, payload: dict) -> None:
    block = f"""

---

## v{payload['version']} — run_experiment ({payload['timestamp_utc']})

### Изменения
- Единый entrypoint; конфиг: `{payload.get('config_path')}`
- Рецепт: {payload.get('recipe')}

### Holdout
- winner_next={payload['winner_next_step']}; winner_weekly={payload['winner_weekly']}
- comparison={json.dumps(payload['comparison'], ensure_ascii=False)}

### Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

### Артефакты
- `reports/run_v{payload['version']}.md`, `run_v{payload['version']}_full.json`
"""
    with path.open("a", encoding="utf-8") as f:
        f.write(block)


def run_from_config(root: Path, config_path: Path, package_version: str) -> dict:
    recipe = json.loads(config_path.read_text(encoding="utf-8"))
    req = recipe.get("require_package_version")
    if req and req != package_version:
        raise SystemExit(
            f"VERSION mismatch: config require_package_version={req}, package={package_version}. "
            "Обновите VERSION/pyproject или уберите require_package_version для архивного конфига."
        )
    # относительный путь конфига для отчёта
    try:
        recipe["_config_path"] = str(config_path.relative_to(root))
    except ValueError:
        recipe["_config_path"] = str(config_path)
    recipe_name = recipe.get("recipe", "softmax_fep_ab")
    if recipe_name == "softmax_fep_ab":
        return run_softmax_fep_ab(root, recipe, package_version)
    raise SystemExit(f"Неизвестный recipe: {recipe_name}")
