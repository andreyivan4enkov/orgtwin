"""Продуктовые операции над мембранами и топологией handover."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd

from orgtwin.policy.softmax import SoftmaxPolicyBundle, next_step_accuracy, prune_membrane_actions, prepare_trace_frame


def membrane_bit_budget(bundle: SoftmaxPolicyBundle, fit_df: pd.DataFrame) -> dict[str, Any]:
    framed, _ = prepare_trace_frame(fit_df, amount_bin_edges=bundle.amount_bin_edges)
    framed["role_id"] = framed["agent"].map(bundle.agent_to_role)
    rows = []
    for role, mask in bundle.role_action_mask.items():
        n = int(mask.sum())
        h = float(np.log2(n)) if n > 1 else 0.0
        n_events = int((framed["role_id"] == role).sum()) if "role_id" in framed.columns else 0
        rows.append({"role_id": role, "membrane_size": n, "H_bits_upper": h, "n_events": n_events})
    rows.sort(key=lambda r: -r["H_bits_upper"])
    return {"roles": rows, "mean_H_bits": float(np.mean([r["H_bits_upper"] for r in rows])) if rows else 0.0}


def prune_and_score(
    bundle: SoftmaxPolicyBundle,
    fit_df: pd.DataFrame,
    hold_df: pd.DataFrame,
    *,
    min_support: int = 30,
    lambda_entropy: float = 0.05,
    agent_col: str | None = None,
    context_col: str | None = None,
) -> dict[str, Any]:
    prep = {"agent_col": agent_col, "context_col": context_col}
    before = next_step_accuracy(bundle, hold_df, **prep)
    bits_before = membrane_bit_budget(bundle, fit_df)
    bundle2 = deepcopy(bundle)
    pruned = prune_membrane_actions(bundle2, fit_df, lambda_entropy=lambda_entropy, min_support=min_support)
    after = next_step_accuracy(bundle2, hold_df, **prep)
    bits_after = membrane_bit_budget(bundle2, fit_df)
    return {
        "pruned": pruned,
        "metrics_before": before,
        "metrics_after": after,
        "bits_before": bits_before,
        "bits_after": bits_after,
        "bundle": bundle2,
    }


def prune_weak_edges(edges: list[dict], min_weight: float = 0.05) -> dict[str, Any]:
    kept, removed = [], []
    for e in edges:
        if float(e.get("weight", 0)) >= min_weight:
            kept.append(e)
        else:
            removed.append(e)
    return {
        "edges": kept,
        "removed": removed,
        "n_kept": len(kept),
        "n_removed": len(removed),
        "min_weight": min_weight,
    }


def suggest_collapse_paths(edges: list[dict], top_n: int = 8) -> list[dict]:
    """Эвристика: пары A→B и B→A с близкими весами — кандидаты на схлопывание."""
    by_pair: dict[tuple[str, str], float] = {}
    for e in edges:
        a, b = str(e["from_agent"]), str(e["to_agent"])
        by_pair[(a, b)] = float(e.get("weight", 0))
    suggestions = []
    seen = set()
    for (a, b), w in by_pair.items():
        if a == b or (b, a) in seen:
            continue
        w2 = by_pair.get((b, a))
        if w2 is None:
            continue
        seen.add((a, b))
        suggestions.append(
            {
                "a": a,
                "b": b,
                "weight_ab": w,
                "weight_ba": w2,
                "hint": "встречный handover — проверить, нужен ли двусторонний канал",
            }
        )
    suggestions.sort(key=lambda x: -(x["weight_ab"] + x["weight_ba"]))
    return suggestions[:top_n]


def topology_diff(before: list[dict], after: list[dict]) -> dict[str, Any]:
    def key(e: dict) -> tuple[str, str]:
        return (str(e["from_agent"]), str(e["to_agent"]))

    bmap = {key(e): e for e in before}
    amap = {key(e): e for e in after}
    added = [amap[k] for k in amap.keys() - bmap.keys()]
    removed = [bmap[k] for k in bmap.keys() - amap.keys()]
    weakened = []
    for k in bmap.keys() & amap.keys():
        dw = float(amap[k].get("weight", 0)) - float(bmap[k].get("weight", 0))
        if abs(dw) >= 0.01:
            weakened.append({"from_agent": k[0], "to_agent": k[1], "delta_weight": dw})
    return {"added": added, "removed": removed, "changed": weakened}
