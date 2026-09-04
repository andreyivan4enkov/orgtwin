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
    DonorAdaptConfig,
    EvalConfig,
    ExperimentConfig,
    FEPPolicyConfig,
    PolicyConfig,
    SimConfig,
    SplitConfig,
    TimingConfig,
)
from orgtwin.diag.entity_field import diagnose_entity_field
from orgtwin.diag.edge_field import diagnose_edge_field
from orgtwin.diag.local_minima import diagnose_local_minima
from orgtwin.policy.counts import next_step_accuracy_counts, train_count_policies
from orgtwin.eval.score import actual_case_durations, evaluate
from orgtwin.ingest.xes_loader import filter_event_table, fit_holdout_split, load_event_table, subsample_case_split
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
from orgtwin.contours import (
    CONTOUR_DIAGNOSTIC,
    CONTOUR_SIMULATOR,
    derived_root,
    infer_contour,
    journal_path,
    reports_root,
    validate_contour_recipe,
)


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
        donor_adapt=DonorAdaptConfig(
            **{k: v for k, v in exp.get("donor_adapt", {}).items() if k in DonorAdaptConfig.__dataclass_fields__}
        ),
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


def run_softmax_fep_ab(root: Path, recipe: dict, package_version: str, contour: str) -> dict:
    """Рецепт: Softmax vs FEP habit_only vs FEP full_efe (контур simulator)."""
    ver = str(recipe["version"])
    cfg = _cfg_from_dict(recipe)
    xes = root / recipe["donor"]["xes_path"]
    derived = derived_root(root, contour)
    reports = reports_root(root, contour)
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    failures: list[dict] = []
    decisions: list[str] = list(recipe.get("decisions_seed", []))
    decisions.append(f"Контур={contour}; scripts/run_simulator.py (версия {ver})")
    decisions.append(f"package_version={package_version}")

    adapt = cfg.donor_adapt
    donor_opts = recipe.get("donor", {})

    print(f"OrgTwin experiment {ver} (package {package_version})")
    print("Загрузка XES…")
    t0 = time.perf_counter()
    df = load_event_table(xes, agent_col=adapt.agent_column or None)
    print(f"  событий={len(df)} ({time.perf_counter()-t0:.1f}s)")

    filter_meta: dict = {}
    time_from = donor_opts.get("time_filter_from")
    drop_agents = donor_opts.get("drop_agents")
    if time_from or drop_agents:
        df, filter_meta = filter_event_table(
            df,
            time_from=time_from,
            drop_agents=tuple(drop_agents) if drop_agents else None,
        )
        decisions.append(f"Фильтр донора: {filter_meta}")
        print(f"  после фильтра: событий={len(df)}")

    fit, hold, split_meta = fit_holdout_split(
        df, fit_months=cfg.split.fit_months, holdout_months=cfg.split.holdout_months
    )
    subsample_meta: dict = {}
    fit_max = donor_opts.get("subsample_fit_cases")
    hold_max = donor_opts.get("subsample_hold_cases")
    if fit_max or hold_max:
        fit, hold, subsample_meta = subsample_case_split(
            fit,
            hold,
            fit_max=fit_max,
            hold_max=hold_max,
            seed=int(donor_opts.get("subsample_seed", cfg.sim.seed)),
        )
        decisions.append(f"Subsample кейсов: {subsample_meta}")
        split_meta = {**split_meta, **subsample_meta}
        print(
            f"  subsample: fit_cases={subsample_meta.get('fit_cases')} "
            f"hold_cases={subsample_meta.get('hold_cases')}"
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
        agent_col=adapt.agent_column or None,
        context_col=adapt.context_column or None,
        role_mode=adapt.role_mode,
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
        agent_col=adapt.agent_column or None,
        context_col=adapt.context_column or None,
        role_mode=adapt.role_mode,
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
        "contour": contour,
        "recipe": recipe.get("recipe", "softmax_fep_ab"),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": recipe.get("_config_path"),
        "config": cfg.to_dict(),
        "split_meta": {**split_meta, "donor_filter": filter_meta},
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
    _append_journal(journal_path(root, contour), payload)
    print(md)
    print(f"\nГотово → reports/{contour}/run_v{ver}.md")
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
- winner_next={payload.get('winner_next_step')}; winner_weekly={payload.get('winner_weekly')}
- comparison={json.dumps(payload['comparison'], ensure_ascii=False)}

### Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

### Артефакты
- `reports/run_v{payload['version']}.md`, `run_v{payload['version']}_full.json`
"""
    with path.open("a", encoding="utf-8") as f:
        f.write(block)


def run_agent_rules(root: Path, recipe: dict, package_version: str, contour: str) -> dict:
    """
    Контур diagnostic: счётчики; softmax только если CE лучше.
    Диагностика локальных минимумов. Без FEP/сима/timing.
    """
    ver = str(recipe["version"])
    cfg = _cfg_from_dict(recipe)
    adapt = cfg.donor_adapt
    xes = root / recipe["donor"]["xes_path"]
    derived = derived_root(root, contour)
    reports = reports_root(root, contour)
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    decisions: list[str] = list(recipe.get("decisions_seed", []))
    decisions.append(f"Контур={contour}; scripts/run_diagnostic.py (версия {ver})")
    decisions.append(f"package_version={package_version}")
    decisions.append("FEP / case-head / stress top-3 / prune_min_support вне критического пути")
    decisions.append("λ не входит в обучение; softmax — только A/B по CE holdout")

    ctx = adapt.context_column or None
    agent_col = adapt.agent_column
    prep = {"agent_col": agent_col, "context_col": ctx}

    print(f"OrgTwin experiment {ver} (package {package_version}) recipe=agent_rules")
    print(f"Донор {cfg.donor_id}; агент={agent_col}; контекст={ctx or 'авто'}; роль={adapt.role_mode}")
    t0 = time.perf_counter()
    df = load_event_table(xes, agent_col=agent_col)
    print(f"  событий={len(df)} ({time.perf_counter()-t0:.1f}s)")

    fit, hold, split_meta = fit_holdout_split(
        df, fit_months=cfg.split.fit_months, holdout_months=cfg.split.holdout_months
    )
    failures: list[dict] = []
    if cfg.split.fit_months != cfg.split.target_fit_months or cfg.split.holdout_months != cfg.split.target_holdout_months:
        failures.append(
            {
                "id": "SPLIT_NOT_TARGET",
                "severity": "limitation",
                "detail": f"split {cfg.split.fit_months}+{cfg.split.holdout_months}, цель {cfg.split.target_fit_months}+{cfg.split.target_holdout_months}",
            }
        )

    print("Обучение счётчиков (backoff)…")
    t1 = time.perf_counter()
    counts_pol = train_count_policies(
        fit,
        agent_col=agent_col,
        context_col=ctx,
        role_mode=adapt.role_mode,
        min_support=adapt.count_min_support,
    )
    print(
        f"  fit_acc={counts_pol.train_metrics['fit_action_accuracy']:.3f} "
        f"CE={counts_pol.train_metrics['cross_entropy']:.3f} ({time.perf_counter()-t1:.1f}s)"
    )

    ns_counts = next_step_accuracy_counts(counts_pol, hold, **prep)
    policies = {
        "counts": {
            "holdout": ns_counts,
            "train": counts_pol.train_metrics,
            "kind": "counts",
        }
    }

    ns_sm = None
    if adapt.compare_softmax:
        print("A/B softmax (не критический путь)…")
        t2 = time.perf_counter()
        sm = train_softmax_policies(
            fit,
            lambda_entropy=cfg.policy.lambda_entropy,
            max_iter=cfg.policy.max_iter,
            random_state=cfg.policy.random_state,
            solver=cfg.policy.solver,
            tol=cfg.policy.tol,
            C=cfg.policy.C,
            agent_col=agent_col,
            context_col=ctx,
            role_mode=adapt.role_mode,
        )
        from orgtwin.policy.softmax import next_step_accuracy as ns_softmax

        ns_sm = ns_softmax(sm, hold, **prep)
        policies["softmax"] = {"holdout": ns_sm, "train": sm.train_metrics, "kind": "softmax"}
        print(
            f"  softmax holdout acc={ns_sm['accuracy']:.3f} CE={ns_sm['cross_entropy']:.3f} "
            f"({time.perf_counter()-t2:.1f}s)"
        )

    ce_counts = ns_counts.get("cross_entropy") or 1e9
    winner = "counts"
    if ns_sm is not None:
        ce_sm = ns_sm.get("cross_entropy") or 1e9
        if ce_sm + 1e-6 < ce_counts:
            winner = "softmax"
            decisions.append(
                f"Softmax CE holdout лучше счётчиков ({ce_sm:.4f} < {ce_counts:.4f}) — политика = softmax"
            )
        else:
            decisions.append(
                f"Счётчики не хуже softmax по CE holdout ({ce_counts:.4f} vs {ce_sm:.4f}) — политика = counts"
            )
    else:
        decisions.append("Политика = counts (softmax выключен)")

    print("Диагностика локальных минимумов…")
    diag = diagnose_local_minima(
        fit,
        agent_col=agent_col,
        context_col=ctx,
        role_mode=adapt.role_mode,
        amount_bin_edges=counts_pol.amount_bin_edges,
        min_input_support=adapt.min_input_support,
        min_unique_action_support=adapt.min_unique_action_support,
        unique_share=adapt.unique_share,
        top1_stuck_threshold=adapt.top1_stuck_threshold,
    )
    n_exclusive = sum(len(v) for v in diag["uncovered_frequent_actions_if_agent_removed"].values())
    decisions.append(
        f"Диагностика: агентов={diag['n_agents']}, "
        f"незаменимых частых действий (уник. носитель)={n_exclusive}"
    )
    print("Диагностика directed edges…")
    edge_field = diagnose_edge_field(
        fit,
        agent_col=agent_col,
        context_col=ctx,
    )
    print("Диагностика entity-edge layer…")
    entity_field = diagnose_entity_field(
        fit,
        agent_col=agent_col,
        context_col=ctx,
        role_mode=adapt.role_mode,
    )
    decisions.append(
        f"Directed edges: E={edge_field['n_directed_edges_nonzero']} "
        f"из {edge_field['n_directed_edges_possible']} возможных"
    )
    decisions.append(
        f"Entity field: сущностей={entity_field['n_entities']}, "
        f"рёбер={entity_field['n_edges']}, типов={entity_field['edge_type_counts']}"
    )
    if adapt.run_sim:
        failures.append(
            {
                "id": "SIM_SKIPPED_BY_DESIGN",
                "severity": "info",
                "detail": "run_sim=true запрошен, но recipe agent_rules не гоняет нагрузку (нет слота занятости)",
            }
        )
        decisions.append("Симуляция нагрузки не запускалась: нет занятости / входного потока как рычага")

    comparison = {
        "next_step_accuracy": {k: v["holdout"]["accuracy"] for k, v in policies.items()},
        "top3_accuracy": {k: v["holdout"]["top3_accuracy"] for k, v in policies.items()},
        "cross_entropy": {k: v["holdout"]["cross_entropy"] for k, v in policies.items()},
        "n": {k: v["holdout"]["n"] for k, v in policies.items()},
    }

    payload = {
        "version": ver,
        "contour": contour,
        "recipe": "agent_rules",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": recipe.get("_config_path"),
        "config": cfg.to_dict(),
        "split_meta": split_meta,
        "policies": {
            k: {"kind": v["kind"], "train": v["train"], "holdout": v["holdout"]} for k, v in policies.items()
        },
        "comparison": comparison,
        "winner_policy": winner,
        "winner_next_step": winner,
        "winner_weekly": None,
        "local_minima_summary": {
            "n_agents": diag["n_agents"],
            "n_agents_with_exclusive_actions": len(diag["uncovered_frequent_actions_if_agent_removed"]),
            "exclusive_action_items": n_exclusive,
            "top_stuck_agents": [
                {
                    "agent_id": a["agent_id"],
                    "n_events": a["n_events"],
                    "mean_H_bits_typical_input": a["mean_H_bits_typical_input"],
                    "stuck_event_fraction": a["stuck_event_fraction"],
                    "n_distinct_actions": a["n_distinct_actions"],
                    "n_role_actions": a["n_role_actions"],
                    "unused_role_actions_n": a["unused_role_actions_n"],
                    "exclusive_n": len(a["exclusive_frequent_actions"]),
                }
                for a in diag["agents"][:15]
            ],
        },
        "edge_field_summary": {
            "n_agents": edge_field["n_agents"],
            "n_directed_edges_nonzero": edge_field["n_directed_edges_nonzero"],
            "n_directed_edges_possible": edge_field["n_directed_edges_possible"],
            "density_directed": edge_field["density_directed"],
            "top_edges": edge_field["top_edges"][:15],
            "top_agents": edge_field["agents"][:15],
            "mutation": edge_field.get("mutation", {}),
        },
        "entity_field_summary": {
            "n_entities": entity_field["n_entities"],
            "n_edges": entity_field["n_edges"],
            "entity_type_counts": entity_field["entity_type_counts"],
            "edge_type_counts": entity_field["edge_type_counts"],
            "top_edges_by_type": {
                k: v[:8] for k, v in entity_field["top_edges_by_type"].items()
            },
        },
        "decisions": decisions,
        "failures": failures,
        "notes_ru": recipe.get("notes_ru", ""),
    }

    (reports / f"run_v{ver}_full.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (reports / f"holdout_metrics_v{ver}.json").write_text(
        json.dumps({"comparison": comparison, "winner": winner}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (derived / f"local_minima_v{ver}.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (derived / f"edge_field_v{ver}.json").write_text(
        json.dumps(edge_field, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (derived / f"entity_field_v{ver}.json").write_text(
        json.dumps(entity_field, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (derived / f"failures_v{ver}.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / f"experiment_config_v{ver}.json").write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = _render_agent_rules_md(payload)
    (reports / f"run_v{ver}.md").write_text(md, encoding="utf-8")
    _append_journal(journal_path(root, contour), payload)
    print(md)
    print(f"\nГотово → reports/{contour}/run_v{ver}.md")
    return payload


def _render_agent_rules_md(payload: dict) -> str:
    c = payload["comparison"]
    arms = list(c.get("next_step_accuracy", {}).keys())

    def fmt(x):
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.4f}"
        return str(x)

    header = "| Метрика | " + " | ".join(arms) + " |"
    sep = "|---------|" + "|".join(["------"] * len(arms)) + "|"
    rows = []
    for metric, key in (("next-step", "next_step_accuracy"), ("top-3", "top3_accuracy"), ("CE", "cross_entropy")):
        rows.append("| " + metric + " | " + " | ".join(fmt(c.get(key, {}).get(a)) for a in arms) + " |")

    stuck = payload.get("local_minima_summary", {}).get("top_stuck_agents", [])[:8]
    stuck_lines = []
    for a in stuck:
        h = a.get("mean_H_bits_typical_input")
        sf = a.get("stuck_event_fraction")
        stuck_lines.append(
            f"- `{a['agent_id']}`: n={a['n_events']}, H≈{fmt(h) if isinstance(h, float) else h}, "
            f"stuck_frac={fmt(sf) if isinstance(sf, float) else sf}, "
            f"действий {a['n_distinct_actions']}/{a['n_role_actions']}, "
            f"уник. частых={a['exclusive_n']}"
        )
    efs = payload.get("edge_field_summary", {})
    top_edges = efs.get("top_edges", [])[:8]
    edge_lines = []
    for e in top_edges:
        top_changed = ""
        if e.get("top_changed_fields"):
            first = e["top_changed_fields"][0]
            top_changed = f", top_changed={first['field']}"
        edge_lines.append(
            f"- `{e['from_agent']} → {e['to_agent']}`: n={e['handover_count']}, "
            f"Pout={fmt(e['p_out'])}, Pin={fmt(e['p_in'])}, "
            f"asym={fmt(e['asymmetry_out_minus_reverse'])}, "
            f"H_from={fmt(e['from_route_entropy_bits'])}{top_changed}"
        )
    mut = efs.get("mutation") or {}
    mut_fields = mut.get("top_changed_fields_global") or []
    mut_field_s = ", ".join(f"`{x['field']}` ({x['count']})" for x in mut_fields[:6]) or "—"
    mut_edges = mut.get("top_mutating_edges_by_mass") or []
    mut_edge_lines = []
    for me in mut_edges[:6]:
        tf = (me.get("top_changed_fields") or [{}])[0].get("field", "—")
        mut_edge_lines.append(
            f"- `{me['from_agent']} → {me['to_agent']}`: n={me['handover_count']}, "
            f"avg_n={fmt(me['avg_n_changed_fields_before_handover'])}, "
            f"mass={fmt(me['mutation_mass'])}, top={tf}"
        )
    bin_lines = []
    for b in mut.get("bins_by_handover_count") or []:
        bin_lines.append(
            f"- `{b['bin']}` (n={b['handover_count_lo']}…{b['handover_count_hi']}): "
            f"рёбер {b['n_edges_with_changed_fields']}/{b['n_edges']}, "
            f"доля={fmt(b['share_edges_with_changed_fields'])}"
        )
    ef = payload.get("entity_field_summary", {})
    entity_lines = []
    for edge_type, items in ef.get("top_edges_by_type", {}).items():
        if not items:
            continue
        first = items[0]
        entity_lines.append(
            f"- `{edge_type}`: топ `{first['from_id']} → {first['to_id']}` "
            f"(n={first['count']}, p={fmt(first['p_out_type'])})"
        )

    return f"""# OrgTwin v{payload['version']}

{payload.get('notes_ru') or 'Рецепт agent_rules: локальные правила + holdout next-step.'}

Рецепт: `{payload.get('recipe')}`. Конфиг: `{payload.get('config_path')}`.
Политика (по CE holdout): **{payload['winner_policy']}**.

## Holdout next-step
{header}
{sep}
{chr(10).join(rows)}

## Локальные минимумы (fit)
Агентов: {payload['local_minima_summary']['n_agents']}; с незаменимыми частыми действиями: {payload['local_minima_summary']['n_agents_with_exclusive_actions']}.

{chr(10).join(stuck_lines) if stuck_lines else '—'}

## Directed Edge Field (fit)
Агентов: {efs.get('n_agents')}; рёбер: {efs.get('n_directed_edges_nonzero')} / {efs.get('n_directed_edges_possible')}; плотность: {fmt(efs.get('density_directed'))}.

{chr(10).join(edge_lines) if edge_lines else '—'}

## Мутации Information на всех рёбрах (fit)
Кандидатов полей: {mut.get('n_candidate_fields', 0)}.  
Рёбер с мутацией: {mut.get('n_edges_with_changed_fields', 0)} / {mut.get('n_edges', 0)} (доля {fmt(mut.get('share_edges_with_changed_fields'))}).  
Handover с мутацией: {mut.get('handover_with_changed_fields', 0)} / {mut.get('handover_total', 0)} (доля {fmt(mut.get('share_handovers_with_changed_fields'))}).  
Взвешенное среднее числа полей: {fmt(mut.get('weighted_avg_n_changed_fields'))}.  
Глобальный топ полей: {mut_field_s}.

Топ рёбер по mutation_mass (avg_n × n):
{chr(10).join(mut_edge_lines) if mut_edge_lines else '— (на ненулевых рёбрах Information не меняется)'}

По tertile handover_count:
{chr(10).join(bin_lines) if bin_lines else '—'}

## Entity-Edge Layer (fit)
Сущностей: {ef.get('n_entities')}; рёбер: {ef.get('n_edges')}.  
Типы сущностей: {ef.get('entity_type_counts')}.  
Типы рёбер: {ef.get('edge_type_counts')}.

{chr(10).join(entity_lines) if entity_lines else '—'}

## Решения
{chr(10).join('- ' + d for d in payload['decisions'])}

## Ограничения
{chr(10).join('- **' + f['id'] + '**: ' + f['detail'] for f in payload['failures']) or '—'}
"""


def run_from_config(
    root: Path,
    config_path: Path,
    package_version: str,
    expected_contour: str | None = None,
) -> dict:
    recipe = json.loads(config_path.read_text(encoding="utf-8"))
    req = recipe.get("require_package_version")
    if req and req != package_version:
        raise SystemExit(
            f"VERSION mismatch: config require_package_version={req}, package={package_version}. "
            "Обновите VERSION/pyproject или уберите require_package_version для архивного конфига."
        )
    contour = validate_contour_recipe(recipe, expected=expected_contour)
    recipe["contour"] = contour
    try:
        recipe["_config_path"] = str(config_path.relative_to(root))
    except ValueError:
        recipe["_config_path"] = str(config_path)
    recipe_name = recipe.get("recipe", "softmax_fep_ab")
    if recipe_name == "softmax_fep_ab":
        return run_softmax_fep_ab(root, recipe, package_version, contour)
    if recipe_name == "agent_rules":
        return run_agent_rules(root, recipe, package_version, contour)
    raise SystemExit(f"Неизвестный recipe: {recipe_name}")
