"""Смены, SLA и каскады отказов — операционный слой аэротрубы."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from orgtwin.config.constants import ExperimentConfig, PolicyConfig, SimConfig, TimingConfig
from orgtwin.sim.queue_des import is_ghost_agent, simulate_queue


@dataclass
class ShiftWindow:
    """Окно доступности: day_of_week 0=пн … 6=вс, часы [start_hour, end_hour)."""

    dow: int
    start_hour: float
    end_hour: float


@dataclass
class ShiftCalendar:
    """agent_id → список окон. Пусто = всегда доступен (допущение)."""

    windows: dict[str, list[ShiftWindow]] = field(default_factory=dict)

    def is_available(self, agent_id: str, t_sec: float, t0: pd.Timestamp) -> bool:
        wins = self.windows.get(str(agent_id))
        if not wins:
            return True
        ts = t0 + pd.Timedelta(seconds=float(t_sec))
        dow = int(ts.dayofweek)
        hour = ts.hour + ts.minute / 60.0
        for w in wins:
            if w.dow == dow and w.start_hour <= hour < w.end_hour:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            aid: [{"dow": w.dow, "start_hour": w.start_hour, "end_hour": w.end_hour} for w in wins]
            for aid, wins in self.windows.items()
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ShiftCalendar":
        if not data:
            return cls()
        windows: dict[str, list[ShiftWindow]] = {}
        for aid, rows in data.items():
            windows[str(aid)] = [
                ShiftWindow(dow=int(r["dow"]), start_hour=float(r["start_hour"]), end_hour=float(r["end_hour"]))
                for r in (rows or [])
            ]
        return cls(windows=windows)


def default_office_shifts(agent_ids: list[str]) -> ShiftCalendar:
    """Пн–Пт 9–18 — допущение для демо."""
    wins = [ShiftWindow(dow=d, start_hour=9.0, end_hour=18.0) for d in range(5)]
    return ShiftCalendar(windows={str(a): list(wins) for a in agent_ids})


def sla_metrics(
    case_durations_sec: dict[str, float],
    sla_hours: float = 72.0,
) -> dict[str, Any]:
    if not case_durations_sec:
        return {"sla_hours": sla_hours, "n": 0, "breach_frac": None, "p50_hours": None, "p90_hours": None}
    arr = np.array(list(case_durations_sec.values()), dtype=float)
    hours = arr / 3600.0
    breach = hours > float(sla_hours)
    return {
        "sla_hours": float(sla_hours),
        "n": int(len(hours)),
        "breach_frac": float(breach.mean()),
        "n_breach": int(breach.sum()),
        "p50_hours": float(np.median(hours)),
        "p90_hours": float(np.percentile(hours, 90)),
        "mean_hours": float(hours.mean()),
    }


def duration_percentiles(case_durations_sec: dict[str, float]) -> dict[str, float | None]:
    if not case_durations_sec:
        return {"p50_sec": None, "p90_sec": None, "mean_sec": None, "n": 0}
    arr = np.array(list(case_durations_sec.values()), dtype=float)
    return {
        "p50_sec": float(np.median(arr)),
        "p90_sec": float(np.percentile(arr, 90)),
        "mean_sec": float(arr.mean()),
        "n": int(len(arr)),
    }


def run_cascade_scenario(
    hold: pd.DataFrame,
    pol,
    *,
    exclude_agents: list[str],
    terminal_prefixes: tuple[str, ...] = (),
    recovery: str = "role_peers",
    sla_hours: float = 72.0,
) -> dict[str, Any]:
    """
    Каскад: исключить агентов; recovery=role_peers — маршрутизация на оставшихся
    (simulate_queue уже переназначает на route_pool).
    """
    cfg = ExperimentConfig(
        policy=PolicyConfig(terminal_prefixes=terminal_prefixes),
        timing=TimingConfig(),
        sim=SimConfig(queue_mode=True, input_flow_multiplier=1.0, agent_capacity=1, max_steps_per_case=30, seed=42),
    )
    base = simulate_queue(hold, pol, cfg=cfg, drop_ghost_agents=True)
    scen = simulate_queue(
        hold, pol, cfg=cfg, drop_ghost_agents=True, exclude_agents=set(exclude_agents)
    )

    def peak(sim) -> tuple[str | None, int]:
        best_a, best_q = None, 0
        for a, s in sim.meta.get("queue_stats", {}).items():
            if is_ghost_agent(a):
                continue
            q = int(s.get("max_queue", 0))
            if q > best_q:
                best_a, best_q = a, q
        return best_a, best_q

    ba, bq = peak(base)
    sa, sq = peak(scen)
    base_sla = sla_metrics(getattr(base, "case_durations_sec", {}) or {}, sla_hours)
    scen_sla = sla_metrics(getattr(scen, "case_durations_sec", {}) or {}, sla_hours)
    return {
        "recovery_policy": recovery,
        "exclude_agents": list(exclude_agents),
        "baseline_peak_queue": bq,
        "baseline_bottleneck": ba,
        "scenario_peak_queue": sq,
        "scenario_bottleneck": sa,
        "delta_peak_queue": sq - bq,
        "baseline_sla": base_sla,
        "scenario_sla": scen_sla,
        "lost_cases_est": max(0, int(base.meta.get("n_cases") or 0) - int(scen.meta.get("n_cases") or 0)),
        "time_to_stabilize_hint": "DES до горизонта; стабилизация = конец сима",
    }
