#!/usr/bin/env python3
"""
Честный стресс очередей: baseline ×1 vs поток ×2.

Использует latency из политики (медиана по логу), без Ridge/case-head.

  .venv/bin/python scripts/run_queue_stress.py
  .venv/bin/python scripts/run_queue_stress.py --config configs/simulator/v0.9.0.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
from orgtwin.ingest.xes_loader import filter_event_table, fit_holdout_split, load_event_table, subsample_case_split
from orgtwin.policy.softmax import train_softmax_policies
from orgtwin.sim.queue_des import simulate_queue


def _cfg_from_recipe(recipe: dict) -> ExperimentConfig:
    exp = recipe.get("experiment", recipe)
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


def load_split(recipe: dict) -> tuple:
    cfg = _cfg_from_recipe(recipe)
    adapt = cfg.donor_adapt
    donor_opts = recipe.get("donor", {})
    xes = ROOT / donor_opts.get("xes_path", "data/raw/BPI_Challenge_2012.xes")
    if not xes.exists() and str(xes).endswith(".xes.gz"):
        xes = Path(str(xes).replace(".xes.gz", ".xes"))
    if not xes.exists():
        raise SystemExit(f"Нет XES: {xes}")

    donor_id = donor_opts.get("id", cfg.donor_id)
    print(f"Загрузка {donor_id}…")
    t0 = time.perf_counter()
    df = load_event_table(xes, agent_col=adapt.agent_column or None)
    print(f"  событий={len(df)} ({time.perf_counter()-t0:.1f}s)")

    time_from = donor_opts.get("time_filter_from")
    if time_from:
        df, fmeta = filter_event_table(df, time_from=time_from)
        print(f"  после фильтра: событий={len(df)} cases={fmeta.get('cases_after_time_filter')}")

    fit, hold, meta = fit_holdout_split(
        df, fit_months=cfg.split.fit_months, holdout_months=cfg.split.holdout_months
    )
    fit_max = donor_opts.get("subsample_fit_cases")
    hold_max = donor_opts.get("subsample_hold_cases")
    if fit_max or hold_max:
        fit, hold, smeta = subsample_case_split(
            fit,
            hold,
            fit_max=fit_max,
            hold_max=hold_max,
            seed=int(donor_opts.get("subsample_seed", cfg.sim.seed)),
        )
        meta = {**meta, **smeta}
        print(f"  subsample: fit={smeta.get('fit_cases')} hold={smeta.get('hold_cases')}")
    else:
        print(f"  hold cases={meta['hold_cases']} events={meta['hold_events']}")

    return fit, hold, meta, cfg, donor_id


def main() -> None:
    p = argparse.ArgumentParser(description="Queue stress ×1 vs ×2")
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/simulator/v0.7.0.json",
        help="JSON с donor/experiment (по умолчанию BPIC2012 v0.7)",
    )
    args = p.parse_args()
    cfg_path = args.config if args.config.is_absolute() else ROOT / args.config
    if not cfg_path.exists():
        raise SystemExit(f"Нет конфига: {cfg_path}")

    recipe = json.loads(cfg_path.read_text(encoding="utf-8"))
    fit, hold, meta, cfg, donor_id = load_split(recipe)

    print("Обучение softmax (маршрутизация)…")
    adapt = cfg.donor_adapt
    t0 = time.perf_counter()
    pol = train_softmax_policies(
        fit,
        max_iter=cfg.policy.max_iter,
        random_state=cfg.policy.random_state,
        solver=cfg.policy.solver,
        tol=cfg.policy.tol,
        C=cfg.policy.C,
        agent_col=adapt.agent_column or None,
        context_col=adapt.context_column or None,
        role_mode=adapt.role_mode,
    )
    print(f"  fit_acc={pol.train_metrics['fit_action_accuracy']:.3f} ({time.perf_counter()-t0:.1f}s)")

    out_dir = ROOT / "reports/simulator"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    max_steps = cfg.sim.max_steps_per_case

    for mult in (1.0, 2.0):
        run_cfg = ExperimentConfig(
            donor_id=cfg.donor_id,
            policy=cfg.policy,
            sim=SimConfig(
                queue_mode=True,
                input_flow_multiplier=mult,
                agent_capacity=1,
                max_steps_per_case=max_steps,
                seed=cfg.sim.seed,
            ),
        )
        label = f"flow_x{mult:.0f}"
        print(f"Симуляция очереди {label}…")
        t1 = time.perf_counter()
        sim = simulate_queue(hold, pol, cfg=run_cfg, max_steps_per_case=max_steps)
        wall = time.perf_counter() - t1
        top = sorted(
            ((a, s["max_queue_length"]) for a, s in sim.meta["queue_stats"].items()),
            key=lambda x: -x[1],
        )[:8]
        results[label] = {
            "wall_sec": wall,
            "max_queue_any": sim.meta["max_queue_length_any_agent"],
            "sum_final_queue": sim.meta["sum_final_queue_length"],
            "n_events": len(sim.events),
            "top_agents_by_max_queue": top,
        }
        print(
            f"  max_queue={sim.meta['max_queue_length_any_agent']} "
            f"final_sum_q={sim.meta['sum_final_queue_length']} "
            f"events={len(sim.events)} wall={wall:.1f}s"
        )
        for ag, q in top[:5]:
            print(f"    {ag}: max_queue={q}")

    slug = donor_id.lower().replace(" ", "_")
    payload = {
        "version": "0.10.1",
        "contour": "simulator",
        "engine": "queue_des",
        "donor": donor_id,
        "config": str(cfg_path.relative_to(ROOT)),
        "split_meta": meta,
        "results": results,
        "note": "×2 = дублирование кейсов на тех же arrival times; метрика — очередь",
    }
    path = out_dir / f"queue_stress_{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОтчёт → {path}")


if __name__ == "__main__":
    main()
