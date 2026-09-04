"""
Диагностика локальных правил и застревания — не оптимизатор.

Для агента:
  H(действие | типичный вход), доля массы на топ-1,
  что есть на мембране роли и чего агент никогда не делает,
  какие частые действия почти никто кроме него не делает.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import log2
from typing import Any, Optional

import pandas as pd

from orgtwin.policy.softmax import prepare_trace_frame


def _entropy_bits(counts: Counter) -> float:
    n = sum(counts.values())
    if n <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / n
        if p > 0:
            h -= p * log2(p)
    return float(h)


def diagnose_local_minima(
    fit_df: pd.DataFrame,
    *,
    agent_col: str = "org:resource",
    context_col: Optional[str] = None,
    role_mode: str = "agent",
    amount_bin_edges: Any = None,
    min_input_support: int = 20,
    min_unique_action_support: int = 30,
    unique_share: float = 0.8,
    top1_stuck_threshold: float = 0.8,
    max_rules_per_agent: int = 12,
) -> dict:
    from orgtwin.ingest.xes_loader import infer_roles_from_frame

    framed, _ = prepare_trace_frame(
        fit_df,
        amount_bin_edges=amount_bin_edges,
        agent_col=agent_col,
        context_col=context_col,
    )
    framed["input_sig"] = (
        framed["prev_activity"].astype(str) + "||" + framed["amount_bin"].astype(str)
    )

    role_actions: dict[str, set[str]] = defaultdict(set)
    agent_role = infer_roles_from_frame(framed, role_mode=role_mode)

    for agent, role, act in zip(
        framed["agent"].astype(str),
        framed["agent"].map(agent_role).astype(str),
        framed["action"].astype(str),
    ):
        role_actions[role].add(act)

    global_act = Counter(framed["action"].astype(str))
    agent_act: dict[str, Counter] = defaultdict(Counter)
    for agent, act in zip(framed["agent"].astype(str), framed["action"].astype(str)):
        agent_act[agent][act] += 1

    agents_out: list[dict] = []
    for agent, g in framed.groupby("agent"):
        agent = str(agent)
        role = agent_role.get(agent, agent)
        n = int(len(g))
        by_input: dict[str, Counter] = defaultdict(Counter)
        for sig, act in zip(g["input_sig"].astype(str), g["action"].astype(str)):
            by_input[sig][act] += 1

        typical = []
        stuck_events = 0
        typical_events = 0
        h_w = 0.0
        for sig, cnt in by_input.items():
            support = sum(cnt.values())
            if support < min_input_support:
                continue
            h = _entropy_bits(cnt)
            top_act, top_n = cnt.most_common(1)[0]
            p1 = top_n / support
            typical_events += support
            h_w += h * support
            if p1 >= top1_stuck_threshold:
                stuck_events += support
            typical.append(
                {
                    "input": sig,
                    "support": int(support),
                    "entropy_bits": h,
                    "top1_action": top_act,
                    "top1_mass": float(p1),
                }
            )
        typical.sort(key=lambda r: (-r["top1_mass"] * r["support"], -r["support"]))
        rules = typical[:max_rules_per_agent]

        used = set(agent_act[agent])
        unused_on_role = sorted(role_actions[role] - used)
        unique_actions = []
        for act, n_a in agent_act[agent].items():
            g_n = global_act[act]
            if g_n < min_unique_action_support:
                continue
            share = n_a / g_n
            if share >= unique_share:
                unique_actions.append(
                    {"action": act, "agent_n": int(n_a), "global_n": int(g_n), "share": float(share)}
                )
        unique_actions.sort(key=lambda x: -x["share"] * x["agent_n"])

        mean_h = (h_w / typical_events) if typical_events else float("nan")
        stuck_frac = (stuck_events / typical_events) if typical_events else float("nan")
        agents_out.append(
            {
                "agent_id": agent,
                "role_id": role,
                "n_events": n,
                "n_distinct_actions": len(used),
                "n_role_actions": len(role_actions[role]),
                "unused_role_actions_n": len(unused_on_role),
                "unused_role_actions_sample": unused_on_role[:15],
                "mean_H_bits_typical_input": mean_h,
                "stuck_event_fraction": stuck_frac,
                "n_typical_inputs": len(typical),
                "max_local_rules": rules,
                "exclusive_frequent_actions": unique_actions[:20],
            }
        )

    agents_out.sort(key=lambda a: (-(a["stuck_event_fraction"] or 0), -a["n_events"]))

    # покрытие: если выключить агента, какие частые действия останутся без носителя
    uncovered_if_removed: dict[str, list[str]] = {}
    for rec in agents_out:
        acts = [x["action"] for x in rec["exclusive_frequent_actions"]]
        if acts:
            uncovered_if_removed[rec["agent_id"]] = acts

    return {
        "min_input_support": min_input_support,
        "top1_stuck_threshold": top1_stuck_threshold,
        "unique_share": unique_share,
        "n_agents": len(agents_out),
        "agents": agents_out,
        "uncovered_frequent_actions_if_agent_removed": uncovered_if_removed,
        "note_ru": (
            "Локальный минимум = высокая поддержка входа и высокая P(топ-1|вход). "
            "Не симуляция нагрузки и не увольнение. "
            "uncovered_* — какие частые действия почти никто кроме агента не делает."
        ),
    }
