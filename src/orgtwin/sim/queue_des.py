"""
Дискретно-событийная симуляция с очередями (M/M/c-подобная механика).

Честная «аэродинамическая труба»:
  - слот занятости (capacity) на агента;
  - FIFO-очередь при занятости;
  - время обслуживания = наблюдаемая latency из политики (не Ridge, не case-head).

Метрика продукта при ×2 потоке — длина очереди и ожидание, не «время в пути».
"""

from __future__ import annotations

import heapq
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from orgtwin.config.constants import DEFAULT, ExperimentConfig
from orgtwin.policy.softmax import SoftmaxPolicyBundle, sample_next_agent
from orgtwin.sim.engine import PolicyBundle, SimResult, _amount_bin_for_row, _batch_sample_actions

GHOST_AGENTS = frozenset({"NONE", "UNKNOWN", "nan", "None", "", "null", "NULL"})


def is_ghost_agent(agent: str) -> bool:
    a = str(agent).strip()
    return (not a) or (a in GHOST_AGENTS)


@dataclass
class _CaseState:
    case_id: str
    agent: str
    prev: str
    amount_bin: str
    step: int = 0
    alive: bool = True
    wait_sec: float = 0.0
    service_sec: float = 0.0


@dataclass
class _AgentServer:
    agent_id: str
    capacity: int
    queue: deque[str] = field(default_factory=deque)
    in_service: int = 0
    max_queue: int = 0
    total_wait_sec: float = 0.0
    total_service_sec: float = 0.0
    n_completed: int = 0


def _service_duration(
    policy: PolicyBundle,
    agent: str,
    action: str,
    fallback_sec: float,
    max_sec: float,
) -> float:
    d = policy.latency_sec.get((agent, action))
    if d is None or d <= 0 or not np.isfinite(d):
        d = fallback_sec
    return float(min(max(1.0, d), max_sec))


def _duplicate_cases_for_flow(
    first: pd.DataFrame,
    multiplier: float,
    rng: np.random.Generator,
    *,
    per_case_mult: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Возвращает расширенный first и map duplicate_id → base_id.

    per_case_mult — локальные множители по case_id (нагрузка на отдел).
    """
    rows = []
    base_map: dict[str, str] = {}

    def n_copies(cid: str) -> int:
        if per_case_mult is not None:
            m = float(per_case_mult.get(cid, 1.0))
        else:
            m = float(multiplier)
        return max(1, int(round(m)))

    any_extra = False
    for _, row in first.iterrows():
        cid = str(row["case:concept:name"])
        n = n_copies(cid)
        if n > 1:
            any_extra = True
        for k in range(n):
            if k == 0:
                rows.append(row)
                base_map[cid] = cid
            else:
                dup = row.copy()
                new_id = f"{cid}__flowx{n}__{k}"
                dup["case:concept:name"] = new_id
                rows.append(dup)
                base_map[new_id] = cid

    if not any_extra and per_case_mult is None and multiplier <= 1.0 + 1e-9:
        return first, {str(r["case:concept:name"]): str(r["case:concept:name"]) for _, r in first.iterrows()}
    return pd.DataFrame(rows).reset_index(drop=True), base_map


def simulate_queue(
    seed_cases: pd.DataFrame,
    policy: PolicyBundle,
    cfg: ExperimentConfig | None = None,
    max_steps_per_case: int | None = None,
    seed: int | None = None,
    capacity_overrides: dict[str, int] | None = None,
    drop_ghost_agents: bool = True,
    exclude_agents: set[str] | list[str] | None = None,
    role_flow_multipliers: dict[str, float] | None = None,
) -> SimResult:
    cfg = cfg or DEFAULT
    scfg = cfg.sim
    max_steps = max_steps_per_case if max_steps_per_case is not None else scfg.max_steps_per_case
    seed = scfg.seed if seed is None else seed
    rng = np.random.default_rng(seed)
    terminal_prefixes = cfg.policy.terminal_prefixes
    capacity = max(1, int(scfg.agent_capacity))
    flow_mult = float(scfg.input_flow_multiplier)
    fallback = float(cfg.timing.default_latency_sec)
    max_service = float(cfg.timing.dt_max_sec)
    horizon = scfg.max_sim_horizon_sec
    excluded = {str(a) for a in (exclude_agents or []) if str(a).strip()}

    known_agents = list(policy.agent_to_role.keys())
    if not known_agents:
        raise RuntimeError("Пустой пул агентов")
    real_agents = [a for a in known_agents if not is_ghost_agent(a) and a not in excluded]
    if drop_ghost_agents and real_agents:
        route_pool = real_agents
    else:
        route_pool = [a for a in known_agents if a not in excluded]
    if not route_pool:
        raise RuntimeError("После исключения агентов пул маршрутизации пуст")

    first = (
        seed_cases.sort_values("time:timestamp")
        .groupby("case:concept:name", as_index=False)
        .first()
    )

    per_case: dict[str, float] | None = None
    if role_flow_multipliers:
        per_case = {}
        for _, row in first.iterrows():
            cid = str(row["case:concept:name"])
            agent0 = str(row.get("org:resource", row.get("agent", "UNKNOWN")))
            role0 = str(policy.agent_to_role.get(agent0, "UNKNOWN"))
            local = float(role_flow_multipliers.get(role0, 1.0))
            per_case[cid] = max(1.0, local) * (flow_mult if flow_mult > 1 else 1.0)
        if all(abs(v - 1.0) < 1e-9 for v in per_case.values()) and flow_mult <= 1.0 + 1e-9:
            per_case = None

    if per_case is not None:
        first, _base_map = _duplicate_cases_for_flow(first, 1.0, rng, per_case_mult=per_case)
    else:
        first, _base_map = _duplicate_cases_for_flow(first, flow_mult, rng)

    t0_wall = first["time:timestamp"].min()
    if horizon is None:
        cal_span = float(
            (seed_cases["time:timestamp"].max() - seed_cases["time:timestamp"].min()).total_seconds()
        )
        horizon = cal_span * max(flow_mult, 1.0) * 4.0 + 86400.0 * 180.0
    horizon_truncated = False
    arrivals: list[tuple[float, str]] = []
    cases: dict[str, _CaseState] = {}
    for _, row in first.iterrows():
        case_id = str(row["case:concept:name"])
        agent = str(row.get("org:resource", row.get("agent", "UNKNOWN")))
        if (
            agent not in policy.agent_to_role
            or agent in excluded
            or (drop_ghost_agents and is_ghost_agent(agent))
        ):
            agent = str(rng.choice(route_pool))
        rel = (pd.Timestamp(row["time:timestamp"]) - t0_wall).total_seconds()
        arrivals.append((float(max(0.0, rel)), case_id))
        cases[case_id] = _CaseState(
            case_id=case_id,
            agent=agent,
            prev="∅",
            amount_bin=_amount_bin_for_row(policy, row),
        )

    overrides = {str(k): max(1, int(v)) for k, v in (capacity_overrides or {}).items()}
    servers: dict[str, _AgentServer] = {
        a: _AgentServer(agent_id=a, capacity=overrides.get(a, capacity))
        for a in known_agents
        if a not in excluded
    }

    events: list[dict] = []
    action_counts: dict[str, int] = defaultdict(int)
    agent_workload: dict[str, int] = defaultdict(int)
    heap: list[tuple[float, int, str, Any]] = []
    seq = 0
    for t_arr, cid in sorted(arrivals):
        heapq.heappush(heap, (t_arr, seq, "arrive", cid))
        seq += 1

    n_terminal = 0
    n_max = 0
    sim_now = 0.0

    def _schedule_complete(agent: str, case_id: str, start_t: float, dur: float) -> None:
        nonlocal seq
        end_t = start_t + dur
        if not np.isfinite(end_t):
            end_t = start_t + max_service
        if horizon is not None:
            end_t = min(end_t, horizon)
        heapq.heappush(heap, (end_t, seq, "complete", (case_id, agent)))
        seq += 1

    def _try_start(agent: str, now: float) -> None:
        srv = servers[agent]
        while srv.in_service < srv.capacity and srv.queue:
            cid = srv.queue.popleft()
            st = cases[cid]
            wait = max(0.0, now - getattr(st, "_queued_at", now))
            st.wait_sec += wait
            srv.total_wait_sec += wait
            actions = _batch_sample_actions(
                policy, [st.prev], [st.amount_bin], [agent], rng
            )
            action = actions[0]
            dur = _service_duration(policy, agent, action, fallback, max_service)
            st._pending_action = action  # type: ignore[attr-defined]
            srv.in_service += 1
            _schedule_complete(agent, cid, now, dur)

    def _request_service(case_id: str, agent: str, now: float) -> None:
        if agent not in servers or agent in excluded or (drop_ghost_agents and is_ghost_agent(agent)):
            agent = str(rng.choice(route_pool))
        st = cases[case_id]
        st.agent = agent
        srv = servers[agent]
        if srv.in_service < srv.capacity:
            actions = _batch_sample_actions(
                policy, [st.prev], [st.amount_bin], [agent], rng
            )
            action = actions[0]
            dur = _service_duration(policy, agent, action, fallback, max_service)
            st._pending_action = action  # type: ignore[attr-defined]
            srv.in_service += 1
            _schedule_complete(agent, case_id, now, dur)
        else:
            st._queued_at = now  # type: ignore[attr-defined]
            srv.queue.append(case_id)
            srv.max_queue = max(srv.max_queue, len(srv.queue))

    while heap:
        now, _, etype, payload = heapq.heappop(heap)
        if horizon is not None and now > horizon:
            horizon_truncated = True
            break
        sim_now = now

        if etype == "arrive":
            cid = str(payload)
            st = cases[cid]
            _request_service(cid, st.agent, now)

        elif etype == "complete":
            cid, agent = payload
            st = cases[cid]
            srv = servers[agent]
            action = getattr(st, "_pending_action", "UNKNOWN")
            if "|" in action:
                act_base = action.split("|", 1)[0]
            else:
                act_base = action
            role = policy.agent_to_role.get(agent, "UNKNOWN")
            dur = _service_duration(policy, agent, action, fallback, max_service)
            st.service_sec += dur
            ts_wall = None
            if now < 86400.0 * 365.0 * 50.0:
                try:
                    ts_wall = t0_wall + pd.Timedelta(seconds=now)
                except (OverflowError, pd.errors.OutOfBoundsTimedelta):
                    ts_wall = None
            events.append(
                {
                    "case:concept:name": cid,
                    "org:resource": agent,
                    "role_id": role,
                    "action": action,
                    "time:timestamp": ts_wall,
                    "t_sec": now,
                    "step": st.step,
                    "dt_sec": dur,
                    "wait_sec": st.wait_sec,
                }
            )
            action_counts[action] += 1
            agent_workload[agent] += 1
            st.prev = act_base
            st.step += 1
            srv.in_service = max(0, srv.in_service - 1)
            srv.total_service_sec += dur
            srv.n_completed += 1

            if any(act_base.startswith(p) for p in terminal_prefixes):
                st.alive = False
                n_terminal += 1
            elif st.step >= max_steps:
                st.alive = False
                n_max += 1
            else:
                nxt = sample_next_agent(policy, agent, rng)
                if (
                    nxt not in policy.agent_to_role
                    or nxt in excluded
                    or (drop_ghost_agents and is_ghost_agent(nxt))
                ):
                    nxt = str(rng.choice(route_pool))
                _request_service(cid, nxt, now)

            _try_start(agent, now)

    case_durations = {cid: st.wait_sec + st.service_sec for cid, st in cases.items()}
    queue_stats = {
        a: {
            "capacity": srv.capacity,
            "max_queue_length": srv.max_queue,
            "final_queue_length": len(srv.queue),
            "in_service_end": srv.in_service,
            "total_wait_sec": srv.total_wait_sec,
            "total_service_sec": srv.total_service_sec,
            "n_completed": srv.n_completed,
        }
        for a, srv in servers.items()
    }
    max_q = max((s["max_queue_length"] for s in queue_stats.values()), default=0)
    sum_q_end = sum(s["final_queue_length"] for s in queue_stats.values())

    return SimResult(
        events=events,
        case_durations_sec=case_durations,
        action_counts=dict(action_counts),
        agent_workload=dict(agent_workload),
        meta={
            "sim_engine": "queue_des",
            "queue_mode": True,
            "agent_capacity": capacity,
            "capacity_overrides": overrides,
            "drop_ghost_agents": drop_ghost_agents,
            "exclude_agents": sorted(excluded),
            "role_flow_multipliers": dict(role_flow_multipliers or {}),
            "input_flow_multiplier": flow_mult,
            "service_time_source": "policy_latency_sec",
            "n_cases": len(cases),
            "n_terminal_stop": n_terminal,
            "n_hit_max_steps": n_max,
            "sim_horizon_sec": sim_now,
            "sim_horizon_limit_sec": horizon,
            "horizon_truncated": horizon_truncated,
            "max_service_sec": max_service,
            "max_queue_length_any_agent": int(max_q),
            "sum_final_queue_length": int(sum_q_end),
            "queue_stats": queue_stats,
            "policy_kind": getattr(policy, "policy_kind", "softmax"),
            "seed": seed,
            "note": "Честная очередь: занятость + буфер; без Ridge/case-head калибровки",
        },
    )
