"""
Общий entity-edge layer для diagnostic-контура.

Сущности:
- agent
- action
- information_field
- membrane

Рёбра направленные и типизированные.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import log2
from typing import Any, Optional

import pandas as pd

from orgtwin.ingest.xes_loader import infer_roles_from_frame
from orgtwin.policy.softmax import prepare_trace_frame


def _entropy_bits(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counter.values():
        p = c / total
        if p > 0:
            h -= p * log2(p)
    return float(h)


def _eid(kind: str, raw_id: str) -> str:
    return f"{kind}:{raw_id}"


def diagnose_entity_field(
    fit_df: pd.DataFrame,
    *,
    agent_col: str = "org:resource",
    context_col: Optional[str] = None,
    role_mode: str = "agent",
    top_k_per_type: int = 20,
) -> dict[str, Any]:
    framed, _ = prepare_trace_frame(
        fit_df,
        agent_col=agent_col,
        context_col=context_col,
    )
    framed = framed.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)
    agent_role = infer_roles_from_frame(framed, role_mode=role_mode)

    info_fields = []
    for col in fit_df.columns:
        if col.startswith("@@"):
            continue
        if col == "time:timestamp":
            continue
        info_fields.append(col)

    role_actions: dict[str, set[str]] = defaultdict(set)
    role_sensors: dict[str, set[str]] = defaultdict(set)
    agent_action_counts: dict[str, Counter[str]] = defaultdict(Counter)
    action_action_counts: Counter[tuple[str, str]] = Counter()
    handover_counts: Counter[tuple[str, str]] = Counter()
    edge_counts: Counter[tuple[str, str, str]] = Counter()
    edge_contexts: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    edge_cases: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    for _, row in framed.iterrows():
        agent = str(row["agent"])
        role = str(agent_role.get(agent, agent))
        act = str(row["action"])
        role_actions[role].add(act)
        for field in info_fields:
            if field in row.index and not pd.isna(row[field]):
                role_sensors[role].add(field)
        agent_action_counts[agent][act] += 1

    # agent -> action
    for agent, acts in agent_action_counts.items():
        total = sum(acts.values())
        for act, n in acts.items():
            ek = (_eid("agent", agent), _eid("action", act), "agent_to_action")
            edge_counts[ek] = int(n)
            edge_contexts[ek]["event_count"] = int(n)
            edge_cases[ek] = set()
            edge_contexts[ek]["share_of_agent_events"] = float(n / total)

    # membrane -> action and membrane -> information_field
    for role, acts in role_actions.items():
        m = _eid("membrane", role)
        for act in acts:
            ek = (m, _eid("action", act), "membrane_to_action")
            edge_counts[ek] = int(sum(agent_action_counts[a][act] for a, r in agent_role.items() if r == role))
        for field in role_sensors[role]:
            ek = (m, _eid("information_field", field), "membrane_to_information_field")
            edge_counts[ek] = 1

    # action -> action and agent -> agent (handover)
    for case_id, g in framed.groupby("case:concept:name", sort=False):
        g = g.reset_index(drop=True)
        actions = g["action"].astype(str).tolist()
        agents = g["agent"].astype(str).tolist()
        prevs = g["prev_activity"].astype(str).tolist()
        ctxs = g["amount_bin"].astype(str).tolist()
        for i in range(len(g) - 1):
            a0 = actions[i]
            a1 = actions[i + 1]
            e1 = (_eid("action", a0), _eid("action", a1), "action_to_action")
            action_action_counts[(a0, a1)] += 1
            edge_counts[e1] = int(action_action_counts[(a0, a1)])
            edge_contexts[e1][f"{prevs[i]}||{ctxs[i]}"] += 1
            edge_cases[e1].add(str(case_id))

            g0 = agents[i]
            g1 = agents[i + 1]
            if g0 != g1:
                e2 = (_eid("agent", g0), _eid("agent", g1), "agent_to_agent")
                handover_counts[(g0, g1)] += 1
                edge_counts[e2] = int(handover_counts[(g0, g1)])
                edge_contexts[e2][f"{a0} => {a1}"] += 1
                edge_cases[e2].add(str(case_id))

    entities = []
    for agent in sorted(agent_role):
        entities.append(
            {
                "entity_id": _eid("agent", agent),
                "entity_type": "agent",
                "raw_id": agent,
                "role_id": str(agent_role.get(agent, agent)),
                "event_count": int(sum(agent_action_counts[agent].values())),
                "n_actions": int(len(agent_action_counts[agent])),
            }
        )
    for act in sorted(framed["action"].astype(str).unique()):
        entities.append(
            {
                "entity_id": _eid("action", act),
                "entity_type": "action",
                "raw_id": act,
                "event_count": int((framed["action"].astype(str) == act).sum()),
            }
        )
    for field in sorted(info_fields):
        entities.append(
            {
                "entity_id": _eid("information_field", field),
                "entity_type": "information_field",
                "raw_id": field,
                "non_null_events": int(fit_df[field].notna().sum()) if field in fit_df.columns else 0,
            }
        )
    for role in sorted(role_actions):
        entities.append(
            {
                "entity_id": _eid("membrane", role),
                "entity_type": "membrane",
                "raw_id": role,
                "n_actions": int(len(role_actions[role])),
                "n_sensors": int(len(role_sensors[role])),
                "complexity_bits_upper": float(log2(len(role_actions[role]))) if len(role_actions[role]) > 1 else 0.0,
            }
        )

    # final edge list with per-type normalization
    totals_by_src_type: dict[tuple[str, str], int] = defaultdict(int)
    for (src, _dst, edge_type), count in edge_counts.items():
        totals_by_src_type[(src, edge_type)] += int(count)

    edges = []
    type_counts = Counter()
    for (src, dst, edge_type), count in edge_counts.items():
        total = totals_by_src_type[(src, edge_type)] or 1
        ctx = edge_contexts.get((src, dst, edge_type), Counter())
        edges.append(
            {
                "from_id": src,
                "to_id": dst,
                "edge_type": edge_type,
                "count": int(count),
                "p_out_type": float(count / total),
                "context_entropy_bits": _entropy_bits(ctx) if ctx else 0.0,
                "case_count": len(edge_cases.get((src, dst, edge_type), set())),
                "top_contexts": [
                    {"context": key, "count": int(n), "share_on_edge": float(n / count)}
                    for key, n in ctx.most_common(5)
                ],
            }
        )
        type_counts[edge_type] += 1

    edges.sort(key=lambda e: (-e["count"], e["edge_type"], e["from_id"], e["to_id"]))
    top_by_type = {}
    for edge_type in sorted(type_counts):
        top_by_type[edge_type] = [e for e in edges if e["edge_type"] == edge_type][:top_k_per_type]

    return {
        "n_entities": len(entities),
        "n_edges": len(edges),
        "entity_type_counts": dict(Counter(e["entity_type"] for e in entities)),
        "edge_type_counts": dict(type_counts),
        "entities": entities,
        "edges": edges,
        "top_edges_by_type": top_by_type,
        "note_ru": (
            "Не только agent→agent: сущности agent/action/information_field/membrane "
            "живут в одном directed field. Вес нормируется внутри edge_type от данного источника."
        ),
    }
