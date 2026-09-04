"""Оптимизатор оргструктуры: жадный поиск под L."""

from __future__ import annotations

import time
from typing import Any

from orgtwin.config.constants import ExperimentConfig, PolicyConfig, SimConfig, TimingConfig
from orgtwin.sim.queue_des import is_ghost_agent, simulate_queue


def compute_L(
    *,
    peak_queue: float,
    sla_breach_frac: float | None,
    mean_H_bits: float | None,
    n_fte: float | None = None,
    weights: dict[str, float] | None = None,
) -> float:
    w = {"queue": 1.0, "sla": 50.0, "H": 0.1, "fte": 0.0}
    if weights:
        w.update({k: float(v) for k, v in weights.items()})
    L = w["queue"] * float(peak_queue)
    if sla_breach_frac is not None:
        L += w["sla"] * float(sla_breach_frac)
    if mean_H_bits is not None:
        L += w["H"] * float(mean_H_bits)
    if n_fte is not None and w.get("fte"):
        L += w["fte"] * float(n_fte)
    return float(L)


def _peak(sim) -> int:
    best = 0
    for a, s in sim.meta.get("queue_stats", {}).items():
        if is_ghost_agent(a):
            continue
        best = max(best, int(s.get("max_queue", 0)))
    return best


def greedy_optimize(
    hold,
    pol,
    *,
    agents: list[dict],
    terminal_prefixes: tuple[str, ...] = (),
    weights: dict[str, float] | None = None,
    max_iters: int = 12,
    wall_sec: float = 45.0,
    sla_hours: float = 72.0,
    mean_H_bits: float | None = None,
) -> dict[str, Any]:
    from orgtwin.api.ops_layer import duration_percentiles, sla_metrics

    t0 = time.perf_counter()
    cfg = ExperimentConfig(
        policy=PolicyConfig(terminal_prefixes=terminal_prefixes),
        timing=TimingConfig(),
        sim=SimConfig(queue_mode=True, input_flow_multiplier=1.0, agent_capacity=1, max_steps_per_case=30, seed=42),
    )
    base_sim = simulate_queue(hold, pol, cfg=cfg, drop_ghost_agents=True)
    base_peak = _peak(base_sim)
    base_sla = sla_metrics(getattr(base_sim, "case_durations_sec", {}) or {}, sla_hours)
    base_L = compute_L(
        peak_queue=base_peak,
        sla_breach_frac=base_sla.get("breach_frac"),
        mean_H_bits=mean_H_bits,
        n_fte=float(len(agents)),
        weights=weights,
    )

    log: list[dict] = []
    best = {
        "L": base_L,
        "peak_queue": base_peak,
        "sla": base_sla,
        "capacities": {},
        "exclude_agents": [],
        "label": "baseline",
    }
    candidates = [dict(best)]

    # топ узких мест
    tops = sorted(
        (
            (a, int(s.get("max_queue", 0)))
            for a, s in base_sim.meta.get("queue_stats", {}).items()
            if not is_ghost_agent(a)
        ),
        key=lambda x: -x[1],
    )[:5]

    actions: list[tuple[str, dict]] = []
    for a, _q in tops:
        actions.append((f"capacity+1:{a}", {"capacities": {a: 2}}))
    if tops:
        actions.append((f"exclude:{tops[0][0]}", {"exclude_agents": [tops[0][0]]}))
    for a, _q in tops[1:3]:
        actions.append((f"exclude:{a}", {"exclude_agents": [a]}))

    for i, (label, patch) in enumerate(actions[:max_iters]):
        if time.perf_counter() - t0 > wall_sec:
            break
        caps = patch.get("capacities")
        excl = set(patch.get("exclude_agents") or [])
        try:
            sim = simulate_queue(
                hold,
                pol,
                cfg=cfg,
                drop_ghost_agents=True,
                capacity_overrides=caps,
                exclude_agents=excl,
            )
        except RuntimeError as e:
            log.append({"iter": i, "label": label, "error": str(e)})
            continue
        peak = _peak(sim)
        sla = sla_metrics(getattr(sim, "case_durations_sec", {}) or {}, sla_hours)
        L = compute_L(
            peak_queue=peak,
            sla_breach_frac=sla.get("breach_frac"),
            mean_H_bits=mean_H_bits,
            n_fte=float(len(agents) - len(excl)),
            weights=weights,
        )
        row = {
            "iter": i,
            "label": label,
            "L": L,
            "peak_queue": peak,
            "sla": sla,
            "durations": duration_percentiles(getattr(sim, "case_durations_sec", {}) or {}),
            "capacities": caps or {},
            "exclude_agents": sorted(excl),
        }
        log.append(row)
        candidates.append(row)
        if L < best["L"]:
            best = row

    candidates.sort(key=lambda x: x["L"])
    return {
        "baseline_L": base_L,
        "best": best,
        "top3": candidates[:3],
        "log": log,
        "weights": weights or {"queue": 1.0, "sla": 50.0, "H": 0.1, "fte": 0.0},
        "wall_sec": round(time.perf_counter() - t0, 2),
    }
