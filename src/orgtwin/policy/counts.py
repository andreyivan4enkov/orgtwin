"""
Локальные правила как счётчики: P(действие | видимая информация, агент).

Backoff (от узкого ключа к широкому), без softmax и без FEP.
Это и есть объект «правило агента», а не логит 1960-х.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from orgtwin.policy.softmax import prepare_trace_frame


@dataclass
class CountPolicyBundle:
    action_classes: list[str]
    agent_to_role: dict[str, str]
    role_action_mask: dict[str, np.ndarray]
    amount_bin_edges: Optional[np.ndarray]
    feature_cols: list[str]
    # ключ backoff → action → count
    tables: dict[tuple[str, ...], dict[str, int]]
    backoff_order: tuple[str, ...]
    min_support: int
    train_metrics: dict = field(default_factory=dict)
    policy_kind: str = "counts"
    latency_sec: dict = field(default_factory=dict)
    handover_probs: dict = field(default_factory=dict)

    def allowed_actions(self, role_id: str) -> list[str]:
        mask = self.role_action_mask.get(role_id)
        if mask is None:
            return list(self.action_classes)
        return [a for a, m in zip(self.action_classes, mask) if m]


def _key_agent_prev_ctx(agent: str, prev: str, ctx: str) -> tuple[str, ...]:
    return ("apc", agent, prev, ctx)


def _key_agent_prev(agent: str, prev: str) -> tuple[str, ...]:
    return ("ap", agent, prev)


def _key_agent(agent: str) -> tuple[str, ...]:
    return ("a", agent)


def _key_global() -> tuple[str, ...]:
    return ("g",)


def _lookup_dist(
    tables: dict[tuple[str, ...], dict[str, int]],
    agent: str,
    prev: str,
    ctx: str,
    min_support: int,
) -> dict[str, int]:
    for key in (
        _key_agent_prev_ctx(agent, prev, ctx),
        _key_agent_prev(agent, prev),
        _key_agent(agent),
        _key_global(),
    ):
        bucket = tables.get(key)
        if bucket and sum(bucket.values()) >= min_support:
            return bucket
    return tables.get(_key_global(), {})


def _normalize(counts: dict[str, int], classes: list[str], mask: Optional[np.ndarray]) -> np.ndarray:
    p = np.zeros(len(classes), dtype=float)
    idx = {c: i for i, c in enumerate(classes)}
    for a, n in counts.items():
        if a in idx:
            p[idx[a]] = float(n)
    if mask is not None and mask.any():
        p = p * mask.astype(float)
    s = p.sum()
    if s <= 0:
        if mask is not None and mask.any():
            p = mask.astype(float)
            p /= p.sum()
        else:
            p[:] = 1.0 / max(len(classes), 1)
        return p
    return p / s


def train_count_policies(
    fit_df: pd.DataFrame,
    *,
    agent_col: str = "org:resource",
    context_col: Optional[str] = None,
    role_mode: str = "activity_prefix",
    min_support: int = 3,
) -> CountPolicyBundle:
    framed, edges = prepare_trace_frame(
        fit_df,
        agent_col=agent_col,
        context_col=context_col,
    )
    from orgtwin.ingest.xes_loader import infer_roles_from_frame

    agent_to_role = infer_roles_from_frame(framed, role_mode=role_mode)
    framed["role_id"] = framed["agent"].map(agent_to_role).fillna("UNKNOWN")

    y = framed["action"].astype(str)
    action_classes = sorted(y.unique().tolist())
    tables: dict[tuple[str, ...], dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for agent, prev, ctx, act in zip(
        framed["agent"].astype(str),
        framed["prev_activity"].astype(str),
        framed["amount_bin"].astype(str),
        y,
    ):
        tables[_key_agent_prev_ctx(agent, prev, ctx)][act] += 1
        tables[_key_agent_prev(agent, prev)][act] += 1
        tables[_key_agent(agent)][act] += 1
        tables[_key_global()][act] += 1

    # заморозить defaultdict
    frozen = {k: dict(v) for k, v in tables.items()}

    role_action_mask: dict[str, np.ndarray] = {}
    for role, g in framed.groupby("role_id"):
        present = set(g["action"].unique())
        role_action_mask[str(role)] = np.array([a in present for a in action_classes], dtype=bool)

    ns = _next_step_on_frame(frozen, framed, action_classes, agent_to_role, role_action_mask, min_support)
    train_metrics = {
        "n_samples": int(len(framed)),
        "n_actions": len(action_classes),
        "n_agents": int(framed["agent"].nunique()),
        "n_tables": len(frozen),
        "min_support": min_support,
        "fit_action_accuracy": ns["accuracy"],
        "fit_top3_accuracy": ns["top3_accuracy"],
        "cross_entropy": ns["cross_entropy"],
        "backoff": "apc → ap → a → global",
        "loss_audit_form": "эмпирический P(action|info,agent); CE на fit",
    }
    return CountPolicyBundle(
        action_classes=action_classes,
        agent_to_role=agent_to_role,
        role_action_mask=role_action_mask,
        amount_bin_edges=edges,
        feature_cols=["prev_activity", "amount_bin", "agent"],
        tables=frozen,
        backoff_order=("apc", "ap", "a", "g"),
        min_support=min_support,
        train_metrics=train_metrics,
    )


def _next_step_on_frame(
    tables: dict[tuple[str, ...], dict[str, int]],
    framed: pd.DataFrame,
    action_classes: list[str],
    agent_to_role: dict[str, str],
    role_action_mask: dict[str, np.ndarray],
    min_support: int,
) -> dict:
    class_index = {c: i for i, c in enumerate(action_classes)}
    y = framed["action"].astype(str).to_numpy()
    agents = framed["agent"].astype(str).to_numpy()
    prevs = framed["prev_activity"].astype(str).to_numpy()
    ctxs = framed["amount_bin"].astype(str).to_numpy()
    correct = 0
    top3 = 0
    nll: list[float] = []
    n = len(framed)
    for i in range(n):
        agent = agents[i]
        counts = _lookup_dist(tables, agent, prevs[i], ctxs[i], min_support)
        role = agent_to_role.get(agent, "UNKNOWN")
        mask = role_action_mask.get(role)
        p = _normalize(counts, action_classes, mask)
        truth = y[i]
        pred_i = int(np.argmax(p))
        if action_classes[pred_i] == truth:
            correct += 1
        top_idx = np.argsort(p)[-3:]
        if truth in class_index and class_index[truth] in top_idx:
            top3 += 1
        if truth in class_index:
            nll.append(-np.log(max(p[class_index[truth]], 1e-12)))
        else:
            nll.append(12.0)
    return {
        "n": int(n),
        "accuracy": float(correct / n) if n else float("nan"),
        "top3_accuracy": float(top3 / n) if n else float("nan"),
        "cross_entropy": float(np.mean(nll)) if nll else float("nan"),
    }


def next_step_accuracy_counts(bundle: CountPolicyBundle, df: pd.DataFrame, **prep_kw: Any) -> dict:
    framed, _ = prepare_trace_frame(df, amount_bin_edges=bundle.amount_bin_edges, **prep_kw)
    known = framed["agent"].isin(bundle.agent_to_role)
    framed = framed[known]
    if framed.empty:
        return {"n": 0, "accuracy": float("nan"), "top3_accuracy": float("nan"), "cross_entropy": float("nan")}
    return _next_step_on_frame(
        bundle.tables,
        framed,
        bundle.action_classes,
        bundle.agent_to_role,
        bundle.role_action_mask,
        bundle.min_support,
    )
