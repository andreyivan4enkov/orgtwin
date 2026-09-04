"""
Расширенный directed edge report между агентами.

Каждое ребро A→B — отдельный объект, не симметричный B→A.
Считаем только соседние смены агента внутри одного кейса.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import log2
from typing import Any, Optional

import pandas as pd

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


def diagnose_edge_field(
    fit_df: pd.DataFrame,
    *,
    agent_col: str = "org:resource",
    context_col: Optional[str] = None,
    top_k_edges: int = 40,
    top_k_actions: int = 5,
    top_k_contexts: int = 5,
    top_k_changed_fields: int = 8,
    min_edge_support: int = 1,
) -> dict[str, Any]:
    framed, _ = prepare_trace_frame(
        fit_df,
        agent_col=agent_col,
        context_col=context_col,
    )
    framed = framed.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)
    framed["input_sig"] = framed["prev_activity"].astype(str) + "||" + framed["amount_bin"].astype(str)

    out_counts: dict[str, Counter[str]] = defaultdict(Counter)
    in_counts: dict[str, Counter[str]] = defaultdict(Counter)
    edge_action_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    edge_context_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    edge_changed_fields_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    edge_changed_fields_total_n: Counter[tuple[str, str]] = Counter()
    edge_changed_fields_transitions: Counter[tuple[str, str]] = Counter()
    global_changed_fields: Counter[str] = Counter()
    edge_cases: dict[tuple[str, str], set[str]] = defaultdict(set)
    edge_prev_actions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    edge_next_actions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    agent_events = Counter(framed["agent"].astype(str))

    exclude_cols = {
        "case:concept:name",
        "concept:name",
        "lifecycle:transition",
        "time:timestamp",
        "prev_activity",
        "action",
        "amount_bin",
        "agent",
        "input_sig",
    }
    # В ряде доноров загрузчик гарантирует наличие `org:resource`,
    # даже если агент задан как `org:group` (и наоборот).
    # Для семантики Information-полей идентификаторы агентов/групп нам не нужны.
    exclude_cols.update({"org:resource", "org:group"})
    exclude_cols.add(agent_col)
    candidate_fields = [c for c in framed.columns if c not in exclude_cols and c != agent_col]

    for _, g in framed.groupby("case:concept:name", sort=False):
        rows = g.reset_index(drop=True)
        agents = rows["agent"].astype(str).tolist()
        actions = rows["action"].astype(str).tolist()
        inputs = rows["input_sig"].astype(str).tolist()
        case_id = str(rows.loc[0, "case:concept:name"])
        for i in range(len(rows) - 1):
            a = agents[i]
            b = agents[i + 1]
            if a == b:
                continue
            edge = (a, b)
            out_counts[a][b] += 1
            in_counts[b][a] += 1
            edge_cases[edge].add(case_id)
            edge_prev_actions[edge][actions[i]] += 1
            edge_next_actions[edge][actions[i + 1]] += 1
            edge_action_counts[edge][f"{actions[i]} => {actions[i + 1]}"] += 1
            edge_context_counts[edge][inputs[i]] += 1
            # Information semantics: какие поля изменились между event i и i+1
            n_changed = 0
            for field in candidate_fields:
                v0 = rows.at[i, field] if field in rows.columns else None
                v1 = rows.at[i + 1, field] if field in rows.columns else None
                # NaN-варианты трактуем как "пусто"
                if pd.isna(v0) and pd.isna(v1):
                    continue
                if pd.isna(v0) != pd.isna(v1):
                    n_changed += 1
                    edge_changed_fields_counts[edge][field] += 1
                    global_changed_fields[field] += 1
                    continue
                # сравнение "как есть": для категориальных/числовых будет stable
                if v0 != v1:
                    n_changed += 1
                    edge_changed_fields_counts[edge][field] += 1
                    global_changed_fields[field] += 1
            if n_changed:
                edge_changed_fields_total_n[edge] += n_changed
                edge_changed_fields_transitions[edge] += 1

    all_agents = sorted(agent_events)
    global_in_share = {
        agent: float(sum(srcs.values())) for agent, srcs in in_counts.items()
    }
    global_in_total = sum(global_in_share.values()) or 1.0

    edges = []
    for a in all_agents:
        total_out = sum(out_counts[a].values())
        h_out = _entropy_bits(out_counts[a]) if total_out else 0.0
        out_sorted = out_counts[a].most_common()
        out_rank = {dst: idx + 1 for idx, (dst, _c) in enumerate(out_sorted)}
        for b in all_agents:
            if a == b:
                continue
            count = int(out_counts[a][b])
            if count < min_edge_support:
                continue
            total_in_b = sum(in_counts[b].values())
            p_out = float(count / total_out) if total_out else 0.0
            p_in = float(count / total_in_b) if total_in_b else 0.0
            back = int(out_counts[b][a])
            p_back = float(back / sum(out_counts[b].values())) if sum(out_counts[b].values()) else 0.0
            base_to = float(global_in_share.get(b, 0.0) / global_in_total)
            lift = float(p_out / base_to) if base_to > 0 else float("inf")
            actions = edge_action_counts[(a, b)].most_common(top_k_actions)
            contexts = edge_context_counts[(a, b)].most_common(top_k_contexts)
            changed_fields_top = edge_changed_fields_counts[(a, b)].most_common(top_k_changed_fields)
            avg_n_changed = (
                float(edge_changed_fields_total_n[(a, b)] / edge_changed_fields_transitions[(a, b)])
                if edge_changed_fields_transitions[(a, b)] > 0
                else 0.0
            )
            edges.append(
                {
                    "from_agent": a,
                    "to_agent": b,
                    "handover_count": count,
                    "case_count": len(edge_cases[(a, b)]),
                    "from_event_count": int(agent_events[a]),
                    "to_event_count": int(agent_events[b]),
                    "p_out": p_out,
                    "p_in": p_in,
                    "p_reverse_out": p_back,
                    "asymmetry_out_minus_reverse": float(p_out - p_back),
                    "lift_vs_global_in": lift,
                    "from_out_degree_nonzero": int(sum(1 for _dst, c in out_counts[a].items() if c > 0)),
                    "to_in_degree_nonzero": int(sum(1 for _src, c in in_counts[b].items() if c > 0)),
                    "from_route_entropy_bits": h_out,
                    "edge_rank_from": int(out_rank[b]),
                    "top_action_pairs": [
                        {"pair": pair, "count": int(n), "share_on_edge": float(n / count)} for pair, n in actions
                    ],
                    "top_contexts": [
                        {"input": sig, "count": int(n), "share_on_edge": float(n / count)} for sig, n in contexts
                    ],
                    "top_prev_actions": [
                        {"action": act, "count": int(n)} for act, n in edge_prev_actions[(a, b)].most_common(top_k_actions)
                    ],
                    "top_next_actions": [
                        {"action": act, "count": int(n)} for act, n in edge_next_actions[(a, b)].most_common(top_k_actions)
                    ],
                    "avg_n_changed_fields_before_handover": avg_n_changed,
                    "top_changed_fields": [
                        {"field": f, "count": int(n), "share_on_edge": float(n / count)} for f, n in changed_fields_top
                    ],
                }
            )

    edges.sort(
        key=lambda e: (
            -e["handover_count"],
            -abs(e["asymmetry_out_minus_reverse"]),
            -e["p_out"],
            e["from_agent"],
            e["to_agent"],
        )
    )
    top_edges = edges[:top_k_edges]

    by_agent = []
    for a in all_agents:
        total_out = sum(out_counts[a].values())
        total_in = sum(in_counts[a].values())
        top_out = out_counts[a].most_common(top_k_actions)
        top_in = in_counts[a].most_common(top_k_actions)
        by_agent.append(
            {
                "agent_id": a,
                "event_count": int(agent_events[a]),
                "out_total": int(total_out),
                "in_total": int(total_in),
                "out_degree_nonzero": int(sum(1 for _dst, c in out_counts[a].items() if c > 0)),
                "in_degree_nonzero": int(sum(1 for _src, c in in_counts[a].items() if c > 0)),
                "route_entropy_bits": _entropy_bits(out_counts[a]) if total_out else 0.0,
                "top_outgoing": [
                    {"to_agent": b, "count": int(c), "share": float(c / total_out) if total_out else 0.0}
                    for b, c in top_out
                ],
                "top_incoming": [
                    {"from_agent": b, "count": int(c), "share": float(c / total_in) if total_in else 0.0}
                    for b, c in top_in
                ],
            }
        )
    by_agent.sort(key=lambda x: (-x["out_total"], -x["route_entropy_bits"], x["agent_id"]))

    density = 0.0
    n = len(all_agents)
    if n > 1:
        density = float(len(edges) / (n * (n - 1)))

    mutation = _summarize_mutations(
        edges,
        candidate_fields=candidate_fields,
        global_changed_fields=global_changed_fields,
        top_k_fields=top_k_changed_fields,
        top_k_edges=top_k_edges,
    )

    return {
        "n_agents": n,
        "n_directed_edges_nonzero": len(edges),
        "n_directed_edges_possible": n * (n - 1),
        "density_directed": density,
        "agents": by_agent,
        "edges": edges,
        "top_edges": top_edges,
        "mutation": mutation,
        "note_ru": (
            "Каждое A→B отдельное directed edge. "
            "B→A не симметризуется. "
            "Рёбра считаются только по соседним сменам агента внутри кейса. "
            "mutation — агрегаты changed Information-полей по всем ненулевым рёбрам, не только top."
        ),
    }


def _summarize_mutations(
    edges: list[dict],
    *,
    candidate_fields: list[str],
    global_changed_fields: Counter[str],
    top_k_fields: int,
    top_k_edges: int,
) -> dict[str, Any]:
    """Глобальная сводка мутаций Information по всем directed рёбрам."""
    n_edges = len(edges)
    n_with = 0
    handover_total = 0
    handover_with = 0
    weighted_avg_n = 0.0
    field_counts: Counter[str] = Counter()
    mutating_slim: list[dict] = []

    for e in edges:
        hc = int(e["handover_count"])
        handover_total += hc
        avg_n = float(e.get("avg_n_changed_fields_before_handover") or 0.0)
        fields = e.get("top_changed_fields") or []
        has = bool(fields) or avg_n > 0
        if has:
            n_with += 1
            handover_with += hc
            weighted_avg_n += avg_n * hc
            mutating_slim.append(
                {
                    "from_agent": e["from_agent"],
                    "to_agent": e["to_agent"],
                    "handover_count": hc,
                    "avg_n_changed_fields_before_handover": avg_n,
                    "mutation_mass": float(avg_n * hc),
                    "top_changed_fields": fields[:3],
                }
            )

    mutating_slim.sort(key=lambda x: (-x["mutation_mass"], -x["handover_count"]))
    by_avg = sorted(
        mutating_slim,
        key=lambda x: (-x["avg_n_changed_fields_before_handover"], -x["handover_count"]),
    )

    bins = _handover_count_bins(edges)
    return {
        "n_candidate_fields": len(candidate_fields),
        "candidate_fields": list(candidate_fields),
        "n_edges": n_edges,
        "n_edges_with_changed_fields": n_with,
        "share_edges_with_changed_fields": float(n_with / n_edges) if n_edges else 0.0,
        "handover_total": handover_total,
        "handover_with_changed_fields": handover_with,
        "share_handovers_with_changed_fields": (
            float(handover_with / handover_total) if handover_total else 0.0
        ),
        "weighted_avg_n_changed_fields": (
            float(weighted_avg_n / handover_with) if handover_with else 0.0
        ),
        "top_changed_fields_global": [
            {"field": f, "count": int(c)} for f, c in global_changed_fields.most_common(top_k_fields)
        ],
        "top_mutating_edges_by_mass": mutating_slim[:top_k_edges],
        "top_mutating_edges_by_avg_n": by_avg[: min(8, top_k_edges)],
        "bins_by_handover_count": bins,
    }


def _handover_count_bins(edges: list[dict]) -> list[dict]:
    """Третили по рангу handover_count (каждое ребро в одном бине)."""
    if not edges:
        return []
    indexed = sorted(enumerate(edges), key=lambda x: int(x[1]["handover_count"]))
    n = len(indexed)
    cuts = (0, n // 3, (2 * n) // 3, n)
    names = ("low", "mid", "high")
    out = []
    for i, name in enumerate(names):
        chunk = indexed[cuts[i] : cuts[i + 1]]
        if not chunk:
            continue
        bucket = [e for _, e in chunk]
        n_with = sum(
            1
            for e in bucket
            if (e.get("top_changed_fields") or float(e.get("avg_n_changed_fields_before_handover") or 0) > 0)
        )
        counts = [int(e["handover_count"]) for e in bucket]
        out.append(
            {
                "bin": name,
                "handover_count_lo": min(counts),
                "handover_count_hi": max(counts),
                "n_edges": len(bucket),
                "n_edges_with_changed_fields": n_with,
                "share_edges_with_changed_fields": float(n_with / len(bucket)),
            }
        )
    return out
