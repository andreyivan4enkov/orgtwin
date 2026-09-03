"""
Симуляция OrgTwin: батч-сэмпл политики (softmax или FEP/EFE), калибровка, стресс.

Ускорение: на каждом шаге все живые кейсы кодируются одним transform (softmax)
или берут π∝exp(−γG) из кэша контекста (FEP).
Калибровка: после прогона масштабируем dt кейса так, чтобы сумма → case-head
(явный костыль; не выдаём за чистую эмерджентность — см. LAB_JOURNAL).
"""

from __future__ import annotations

from collections import defaultdict
from copy import copy
from dataclasses import dataclass, field
from typing import Any, Optional, Union

import numpy as np
import pandas as pd

from orgtwin.config.constants import DEFAULT, ExperimentConfig
from orgtwin.ir.basis import OrgGraph
from orgtwin.policy.fep import FEPPolicyBundle, batch_sample_actions_fep
from orgtwin.policy.softmax import SoftmaxPolicyBundle, sample_next_agent
from orgtwin.policy.timing import TimingModel

PolicyBundle = Union[SoftmaxPolicyBundle, FEPPolicyBundle]


@dataclass
class SimResult:
    events: list[dict]
    case_durations_sec: dict[str, float]
    action_counts: dict[str, int]
    agent_workload: dict[str, int]
    meta: dict = field(default_factory=dict)


def _amount_bin_for_row(bundle: PolicyBundle, row: pd.Series) -> str:
    amount_col = "case:AMOUNT_REQ" if "case:AMOUNT_REQ" in row.index else (
        "AMOUNT_REQ" if "AMOUNT_REQ" in row.index else None
    )
    if amount_col is None or bundle.amount_bin_edges is None:
        return "0"
    val = pd.to_numeric(row.get(amount_col), errors="coerce")
    if pd.isna(val):
        return "0"
    edges = bundle.amount_bin_edges
    return str(int(np.digitize([float(val)], edges[1:-1], right=True)[0]))


def _batch_sample_actions(
    policy: PolicyBundle,
    prevs: list[Any],
    amount_bins: list[Any],
    agents: list[str],
    rng: np.random.Generator,
) -> list[str]:
    """Сэмпл Action: FEP (EFE) или softmax (батч-encode)."""
    if not agents:
        return []
    kind = getattr(policy, "policy_kind", "softmax")
    if isinstance(kind, str) and kind.startswith("fep"):
        return batch_sample_actions_fep(policy, prevs, amount_bins, agents, rng)  # type: ignore[arg-type]

    assert isinstance(policy, SoftmaxPolicyBundle)
    rows = pd.DataFrame(
        {
            "prev_activity": [str(p if p is not None else "∅") for p in prevs],
            "amount_bin": [str(a if a is not None else "0") for a in amount_bins],
            "agent": [str(a) for a in agents],
        }
    )
    X = policy.encoder.transform(rows[policy.feature_cols].astype(str))
    proba = policy.model.predict_proba(X)
    out: list[str] = []
    for i, agent in enumerate(agents):
        p = proba[i].astype(float).copy()
        role = policy.agent_to_role.get(str(agent), "UNKNOWN")
        mask = policy.role_action_mask.get(role)
        if mask is not None and mask.any():
            p = p * mask.astype(float)
            s = p.sum()
            if s > 0:
                p /= s
            else:
                p = mask.astype(float) / mask.sum()
        idx = int(rng.choice(len(policy.action_classes), p=p))
        out.append(policy.action_classes[idx])
    return out


def _batch_predict_dt(
    timing: TimingModel | None,
    policy: PolicyBundle,
    prevs: list[Any],
    actions: list[str],
    agents: list[str],
    amount_bins: list[Any],
    default_latency: float,
) -> np.ndarray:
    n = len(actions)
    if timing is None or n == 0:
        dts = []
        for ag, act in zip(agents, actions):
            dts.append(policy.latency_sec.get((ag, act), default_latency))
        return np.array(dts, dtype=float)
    rows = pd.DataFrame(
        {
            "prev_activity": [str(p if p is not None else "∅") for p in prevs],
            "action": [str(a) for a in actions],
            "agent": [str(a) for a in agents],
            "amount_bin": [str(b if b is not None else "0") for b in amount_bins],
        }
    )
    X = timing.encoder.transform(rows[timing.feature_cols].astype(str))
    log_dt = timing.model.predict(X)
    dt = np.expm1(log_dt)
    dt = np.clip(dt, 1e-3, timing.cfg.dt_max_sec)
    return dt.astype(float)


def apply_duration_calibration(
    events: list[dict],
    case_durations: dict[str, float],
    target_durations: dict[str, float],
) -> tuple[list[dict], dict[str, float], dict]:
    """
    Масштабирует временную ось кейса: sum(dt) → target из case-head.
    Возвращает новые events/durations + meta по калибровке.
    """
    by_case: dict[str, list[int]] = defaultdict(list)
    for i, e in enumerate(events):
        by_case[e["case:concept:name"]].append(i)

    scales = {}
    skipped = 0
    new_events = [dict(e) for e in events]
    new_durs = dict(case_durations)

    for case_id, idxs in by_case.items():
        target = target_durations.get(case_id)
        cur = case_durations.get(case_id, 0.0)
        if target is None or cur <= 1e-6:
            skipped += 1
            continue
        scale = float(target) / float(cur)
        scales[case_id] = scale
        # пересчитать timestamps от t0
        t0 = new_events[idxs[0]]["time:timestamp"] - pd.Timedelta(seconds=float(new_events[idxs[0]]["t_sec"]))
        acc = 0.0
        for j in idxs:
            dt = float(new_events[j].get("dt_sec", 0.0)) * scale
            acc += dt
            new_events[j]["dt_sec"] = dt
            new_events[j]["t_sec"] = acc
            new_events[j]["time:timestamp"] = t0 + pd.Timedelta(seconds=acc)
            new_events[j]["duration_calibrated"] = True
        new_durs[case_id] = acc

    meta = {
        "calibration": "scale_dt_to_case_head",
        "n_scaled": len(scales),
        "n_skipped": skipped,
        "scale_median": float(np.median(list(scales.values()))) if scales else float("nan"),
        "scale_p10": float(np.percentile(list(scales.values()), 10)) if scales else float("nan"),
        "scale_p90": float(np.percentile(list(scales.values()), 90)) if scales else float("nan"),
        "note": "Не чистая эмерджентность; явная калибровка под case-level head",
    }
    return new_events, new_durs, meta


def disable_agents(policy: PolicyBundle, agent_ids: set[str]) -> PolicyBundle:
    """Стресс: убрать агентов из пула (копия ссылок + фильтр handover/ролей)."""
    p = copy(policy)
    p.agent_to_role = {a: r for a, r in policy.agent_to_role.items() if a not in agent_ids}
    p.handover_probs = {}
    for a, dist in policy.handover_probs.items():
        if a in agent_ids:
            continue
        filtered = {b: w for b, w in dist.items() if b not in agent_ids}
        if not filtered:
            continue
        s = sum(filtered.values())
        p.handover_probs[a] = {b: w / s for b, w in filtered.items()}
    p.latency_sec = {k: v for k, v in policy.latency_sec.items() if k[0] not in agent_ids}
    p.train_metrics = dict(policy.train_metrics)
    p.train_metrics["stress_disabled_agents"] = sorted(agent_ids)
    if isinstance(p, FEPPolicyBundle):
        from orgtwin.policy.fep import clear_fep_caches

        p._cache_pi = {}
        p._cache_G = {}
        clear_fep_caches(p)
    return p


def top_agents_by_workload(workload: dict[str, int], n: int) -> list[str]:
    return [a for a, _ in sorted(workload.items(), key=lambda x: -x[1])[:n]]


def simulate_batch(
    seed_cases: pd.DataFrame,
    policy: PolicyBundle,
    timing: TimingModel | None = None,
    cfg: ExperimentConfig | None = None,
    max_steps_per_case: int | None = None,
    seed: int | None = None,
    target_durations: dict[str, float] | None = None,
    calibrate_duration: bool = False,
) -> SimResult:
    cfg = cfg or DEFAULT
    max_steps = max_steps_per_case if max_steps_per_case is not None else cfg.sim.max_steps_per_case
    seed = cfg.sim.seed if seed is None else seed
    rng = np.random.default_rng(seed)
    tcfg = cfg.timing
    terminal_prefixes = cfg.policy.terminal_prefixes
    known_agents = list(policy.agent_to_role.keys())
    if not known_agents:
        raise RuntimeError("Пустой пул агентов после стресса")

    first = (
        seed_cases.sort_values("time:timestamp")
        .groupby("case:concept:name", as_index=False)
        .first()
    )

    # состояние кейсов
    live_ids: list[str] = []
    state: dict[str, dict] = {}
    for _, row in first.iterrows():
        case_id = str(row["case:concept:name"])
        agent = str(row["org:resource"])
        if agent not in policy.agent_to_role:
            agent = str(rng.choice(known_agents))
        t0 = pd.Timestamp(row["time:timestamp"])
        state[case_id] = {
            "agent": agent,
            "prev": "∅",
            "amount_bin": _amount_bin_for_row(policy, row),
            "t0": t0,
            "t_abs": t0,
            "t_sec": 0.0,
            "step": 0,
            "alive": True,
        }
        live_ids.append(case_id)

    events: list[dict] = []
    action_counts: dict[str, int] = defaultdict(int)
    agent_workload: dict[str, int] = defaultdict(int)
    n_terminal = 0
    n_max = 0

    for _step in range(max_steps):
        batch = [c for c in live_ids if state[c]["alive"]]
        if not batch:
            break
        prevs = [state[c]["prev"] for c in batch]
        abins = [state[c]["amount_bin"] for c in batch]
        agents = [state[c]["agent"] for c in batch]
        actions = _batch_sample_actions(policy, prevs, abins, agents, rng)
        dts = _batch_predict_dt(
            timing, policy, prevs, actions, agents, abins, tcfg.default_latency_sec
        )
        lo, hi = tcfg.latency_noise_low, tcfg.latency_noise_high
        if lo != 1.0 or hi != 1.0:
            dts = dts * rng.uniform(lo, hi, size=len(dts))

        for c, action, dt, prev, agent in zip(batch, actions, dts, prevs, agents):
            st = state[c]
            dt = float(max(1e-3, dt))
            st["t_sec"] += dt
            st["t_abs"] = st["t0"] + pd.Timedelta(seconds=st["t_sec"])
            if "|" in action:
                act_base = action.split("|", 1)[0]
            else:
                act_base = action
            role = policy.agent_to_role.get(agent, "UNKNOWN")
            events.append(
                {
                    "case:concept:name": c,
                    "org:resource": agent,
                    "role_id": role,
                    "action": action,
                    "time:timestamp": st["t_abs"],
                    "t_sec": st["t_sec"],
                    "step": st["step"],
                    "dt_sec": dt,
                }
            )
            action_counts[action] += 1
            agent_workload[agent] += 1
            st["prev"] = act_base
            st["step"] += 1

            if any(act_base.startswith(p) for p in terminal_prefixes):
                st["alive"] = False
                n_terminal += 1
            else:
                st["agent"] = sample_next_agent(policy, agent, rng)
                if st["agent"] not in policy.agent_to_role:
                    st["agent"] = str(rng.choice(known_agents))

        # кто упёрся в max на последней итерации — посчитаем после цикла

    case_durations = {c: float(state[c]["t_sec"]) for c in state}
    for c, st in state.items():
        if st["alive"]:
            n_max += 1

    cal_meta = {}
    if calibrate_duration and target_durations:
        events, case_durations, cal_meta = apply_duration_calibration(
            events, case_durations, target_durations
        )

    return SimResult(
        events=events,
        case_durations_sec=case_durations,
        action_counts=dict(action_counts),
        agent_workload=dict(agent_workload),
        meta={
            "max_steps_per_case": max_steps,
            "n_cases": len(state),
            "n_hit_max_steps": int(n_max),
            "n_terminal_stop": int(n_terminal),
            "timing_used": timing is not None,
            "batch_encode": getattr(policy, "policy_kind", "softmax") != "fep_efe",
            "policy_kind": getattr(policy, "policy_kind", "softmax"),
            "calibrate_duration": bool(calibrate_duration),
            "latency_noise": [tcfg.latency_noise_low, tcfg.latency_noise_high],
            "seed": seed,
            **cal_meta,
        },
    )


# обратная совместимость имени
def simulate(*args, **kwargs):
    return simulate_batch(*args, **kwargs)


def build_org_from_policy(
    fit_df: pd.DataFrame,
    policy: PolicyBundle,
    donor_id: str = "BPIC2012",
) -> OrgGraph:
    from orgtwin.decompose.dof import build_actions_catalog, build_information_schema
    from orgtwin.ir.basis import Action, InformationAtom, Membrane, NeuroAutomaton
    from orgtwin.policy.softmax import prepare_trace_frame

    schema = build_information_schema(fit_df)
    for key in ("prev_activity", "amount_bin"):
        if key not in schema:
            schema[key] = InformationAtom(key=key, dtype="categorical", readable=True, writable=False)

    catalog = build_actions_catalog(fit_df)
    for name in policy.action_classes:
        if name not in catalog:
            writes = ("concept:name", "lifecycle:transition") if "|" in name else ("concept:name",)
            life = name.split("|", 1)[1] if "|" in name else None
            catalog[name] = Action(
                name=name,
                preconditions=("case:concept:name", "prev_activity"),
                writes=writes,
                bits=1,
                lifecycle=life,
            )

    membranes: dict[str, Membrane] = {}
    for role, mask in policy.role_action_mask.items():
        acts = tuple(catalog[a] for a, m in zip(policy.action_classes, mask) if m and a in catalog)
        sensors = tuple(
            schema[k]
            for k in ("prev_activity", "amount_bin", "case:AMOUNT_REQ", "case:concept:name")
            if k in schema
        )
        membranes[role] = Membrane(role_id=role, sensors=sensors, actions=acts)

    framed, _ = prepare_trace_frame(fit_df, amount_bin_edges=policy.amount_bin_edges)
    counts = framed.groupby("agent").size().to_dict()

    automata = {}
    for agent, role in policy.agent_to_role.items():
        m = membranes.get(role) or Membrane(role_id=role, sensors=(), actions=())
        lat = {
            a: policy.latency_sec[(agent, a)]
            for a in policy.action_classes
            if (agent, a) in policy.latency_sec
        }
        automata[agent] = NeuroAutomaton(
            agent_id=agent,
            role_id=role,
            membrane=m,
            rules=[],
            action_latency_sec=lat,
            event_count=int(counts.get(agent, 0)),
        )

    handovers = {}
    for a, dist in policy.handover_probs.items():
        for b, p in dist.items():
            if a != b:
                handovers[(a, b)] = int(round(p * 1000))

    return OrgGraph(
        donor_id=donor_id,
        automata=automata,
        handovers=handovers,
        information_schema=schema,
        actions_catalog=catalog,
    )
