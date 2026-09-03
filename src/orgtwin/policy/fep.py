"""
Политика активного вывода (Friston) — OrgTwin ≥0.6.

Исправления относительно 0.5.0 (кривой паритет):
  - Habit на уровне **agent** (как agent в softmax), backoff: agent → role → global
  - Переходы q(o'|…) с backoff: (prev,abin,agent,action) → (prev,abin,action)
  - Предпочтения C(o|prev,abin,role), не только маргинал роли
  - Подбор (γ, w_risk, w_amb, w_habit) по **fit** next-step (не holdout)

G(a|I,agent) = w_r·Risk + w_a·Ambiguity − w_h·ln P_habit
π(a) ∝ exp(−γ G) внутри мембраны роли.

Генеративка: Dirichlet–Categorical, без sklearn LR.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from orgtwin.policy.softmax import prepare_trace_frame


@dataclass
class FEPConfig:
    """Константы FEP; любое изменение — в LAB_JOURNAL."""

    dirichlet_alpha: float = 0.5
    gamma_precision: float = 4.0
    preference_power: float = 1.0
    habit_weight: float = 1.0
    ambiguity_weight: float = 0.0
    risk_weight: float = 0.0
    empty_transition_entropy: float = 3.0
    # habit_only: Risk=Amb=0; full: все веса из конфига / тюнинга
    mode: str = "habit_only"  # habit_only | full_efe


@dataclass
class FEPPolicyBundle:
    action_classes: list[str]
    role_action_mask: dict[str, np.ndarray]
    agent_to_role: dict[str, str]
    latency_sec: dict[tuple[str, str], float]
    handover_probs: dict[str, dict[str, float]]
    amount_bin_edges: Optional[np.ndarray]
    train_metrics: dict = field(default_factory=dict)
    policy_kind: str = "fep_efe"
    fep_cfg: FEPConfig = field(default_factory=FEPConfig)
    outcome_classes: list[str] = field(default_factory=list)
    ln_C_by_ctx: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    ln_C_by_role: dict[str, np.ndarray] = field(default_factory=dict)
    habit_by_agent: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    habit_by_role: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    habit_global: dict[tuple[str, str], np.ndarray] = field(default_factory=dict)
    trans_by_agent: dict[tuple[str, str, str, str], np.ndarray] = field(default_factory=dict)
    trans_by_ctx: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    _cache_pi: dict = field(default_factory=dict, repr=False)
    _cache_G: dict = field(default_factory=dict, repr=False)


def _infer_roles(df: pd.DataFrame) -> dict[str, str]:
    from collections import Counter, defaultdict as dd

    from orgtwin.ingest.xes_loader import infer_role

    votes: dict[str, Counter] = dd(Counter)
    for agent, act in zip(df["org:resource"].astype(str), df["concept:name"].astype(str)):
        votes[agent][infer_role(act)] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def _dirichlet_mean(counts: np.ndarray, alpha: float) -> np.ndarray:
    p = counts.astype(float) + alpha
    s = p.sum()
    if s <= 0:
        return np.ones_like(p) / max(len(p), 1)
    return p / s


def _entropy(p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1.0)
    p = p / p.sum()
    return float(-np.sum(p * np.log(p)))


def _kl(q: np.ndarray, p: np.ndarray) -> float:
    q = np.clip(q, 1e-12, 1.0)
    p = np.clip(p, 1e-12, 1.0)
    q = q / q.sum()
    p = p / p.sum()
    return float(np.sum(q * (np.log(q) - np.log(p))))


def clear_fep_caches(bundle: FEPPolicyBundle) -> None:
    bundle._cache_pi.clear()
    bundle._cache_G.clear()


def _habit_probs(bundle: FEPPolicyBundle, prev: str, abin: str, agent: str, role: str) -> np.ndarray:
    cfg = bundle.fep_cfg
    n_a = len(bundle.action_classes)
    key_a = (prev, abin, agent)
    if key_a in bundle.habit_by_agent:
        return _dirichlet_mean(bundle.habit_by_agent[key_a], cfg.dirichlet_alpha)
    key_r = (prev, abin, role)
    if key_r in bundle.habit_by_role:
        return _dirichlet_mean(bundle.habit_by_role[key_r], cfg.dirichlet_alpha)
    key_g = (prev, abin)
    if key_g in bundle.habit_global:
        return _dirichlet_mean(bundle.habit_global[key_g], cfg.dirichlet_alpha)
    return np.ones(n_a) / n_a


def _transition_q(
    bundle: FEPPolicyBundle, prev: str, abin: str, agent: str, action: str
) -> tuple[np.ndarray, bool]:
    cfg = bundle.fep_cfg
    n_o = len(bundle.outcome_classes)
    key_a = (prev, abin, agent, action)
    tc = bundle.trans_by_agent.get(key_a)
    if tc is not None and tc.sum() > 0:
        return _dirichlet_mean(tc, cfg.dirichlet_alpha), False
    key_c = (prev, abin, action)
    tc = bundle.trans_by_ctx.get(key_c)
    if tc is not None and tc.sum() > 0:
        return _dirichlet_mean(tc, cfg.dirichlet_alpha), False
    return np.ones(n_o) / max(n_o, 1), True


def _preference_C(bundle: FEPPolicyBundle, prev: str, abin: str, role: str) -> np.ndarray:
    key = (prev, abin, role)
    if key in bundle.ln_C_by_ctx:
        p = np.exp(bundle.ln_C_by_ctx[key])
        return p / p.sum()
    if role in bundle.ln_C_by_role:
        p = np.exp(bundle.ln_C_by_role[role])
        return p / p.sum()
    n_o = len(bundle.outcome_classes)
    return np.ones(n_o) / max(n_o, 1)


def expected_free_energy(
    bundle: FEPPolicyBundle,
    prev: str,
    amount_bin: str,
    agent: str,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    prev, abin, agent = str(prev), str(amount_bin), str(agent)
    cache_key = (
        prev,
        abin,
        agent,
        bundle.fep_cfg.mode,
        bundle.fep_cfg.gamma_precision,
        bundle.fep_cfg.risk_weight,
        bundle.fep_cfg.ambiguity_weight,
        bundle.fep_cfg.habit_weight,
    )
    if cache_key in bundle._cache_G:
        return bundle._cache_G[cache_key]

    cfg = bundle.fep_cfg
    role = bundle.agent_to_role.get(agent, "UNKNOWN")
    n_a = len(bundle.action_classes)
    G = np.full(n_a, np.inf, dtype=float)
    risk_v = np.zeros(n_a)
    amb_v = np.zeros(n_a)
    hab_v = np.zeros(n_a)

    mask = bundle.role_action_mask.get(role)
    if mask is None:
        mask = np.ones(n_a, dtype=bool)

    habit_p = _habit_probs(bundle, prev, abin, agent, role)
    C = _preference_C(bundle, prev, abin, role)

    w_r = 0.0 if cfg.mode == "habit_only" else cfg.risk_weight
    w_a = 0.0 if cfg.mode == "habit_only" else cfg.ambiguity_weight
    w_h = cfg.habit_weight

    for i, act in enumerate(bundle.action_classes):
        if not mask[i]:
            continue
        habit = float(np.log(max(habit_p[i], 1e-12)))
        hab_v[i] = habit
        if w_r == 0.0 and w_a == 0.0:
            risk = amb = 0.0
        else:
            q, empty = _transition_q(bundle, prev, abin, agent, act)
            amb = cfg.empty_transition_entropy if empty else _entropy(q)
            risk = _kl(q, C)
        risk_v[i] = risk
        amb_v[i] = amb
        G[i] = w_r * risk + w_a * amb - w_h * habit

    comps = {"risk": risk_v, "ambiguity": amb_v, "habit": hab_v}
    bundle._cache_G[cache_key] = (G, comps)
    return G, comps


def policy_proba_fep(
    bundle: FEPPolicyBundle,
    prev: str,
    amount_bin: str,
    agent: str,
) -> np.ndarray:
    prev, abin, agent = str(prev), str(amount_bin), str(agent)
    cache_key = (
        prev,
        abin,
        agent,
        bundle.fep_cfg.mode,
        bundle.fep_cfg.gamma_precision,
        bundle.fep_cfg.risk_weight,
        bundle.fep_cfg.ambiguity_weight,
        bundle.fep_cfg.habit_weight,
    )
    if cache_key in bundle._cache_pi:
        return bundle._cache_pi[cache_key]

    G, _ = expected_free_energy(bundle, prev, abin, agent)
    finite = np.isfinite(G)
    if not finite.any():
        p = np.ones(len(G)) / len(G)
        bundle._cache_pi[cache_key] = p
        return p
    g_ok = G[finite]
    g_shift = g_ok - np.min(g_ok)
    logits = -bundle.fep_cfg.gamma_precision * g_shift
    ex = np.exp(logits - np.max(logits))
    p = np.zeros_like(G)
    p[finite] = ex / ex.sum()
    bundle._cache_pi[cache_key] = p
    return p


def batch_sample_actions_fep(
    bundle: FEPPolicyBundle,
    prevs: list[Any],
    amount_bins: list[Any],
    agents: list[str],
    rng: np.random.Generator,
) -> list[str]:
    out: list[str] = []
    for prev, abin, agent in zip(prevs, amount_bins, agents):
        p = policy_proba_fep(
            bundle,
            str(prev if prev is not None else "∅"),
            str(abin if abin is not None else "0"),
            str(agent),
        )
        idx = int(rng.choice(len(bundle.action_classes), p=p))
        out.append(bundle.action_classes[idx])
    return out


def next_step_accuracy_fep(
    bundle: FEPPolicyBundle,
    df: pd.DataFrame,
    with_efe_components: bool = False,
    max_rows: int | None = None,
) -> dict:
    framed, _ = prepare_trace_frame(df, amount_bin_edges=bundle.amount_bin_edges)
    known = framed["agent"].isin(bundle.agent_to_role)
    framed = framed[known]
    if max_rows is not None and len(framed) > max_rows:
        framed = framed.sample(n=max_rows, random_state=42)
    if framed.empty:
        return {
            "n": 0,
            "accuracy": float("nan"),
            "top3_accuracy": float("nan"),
            "cross_entropy": float("nan"),
            "mean_G_truth": float("nan"),
        }

    class_index = {c: i for i, c in enumerate(bundle.action_classes)}
    prevs = framed["prev_activity"].astype(str).to_numpy()
    abins = framed["amount_bin"].astype(str).to_numpy()
    agents = framed["agent"].astype(str).to_numpy()
    y = framed["action"].astype(str).to_numpy()

    correct = top3 = 0
    nll: list[float] = []
    G_truth: list[float] = []
    risks: list[float] = []
    ambs: list[float] = []
    habs: list[float] = []

    for i in range(len(framed)):
        p = policy_proba_fep(bundle, prevs[i], abins[i], agents[i])
        G, comp = expected_free_energy(bundle, prevs[i], abins[i], agents[i])
        if bundle.action_classes[int(np.argmax(p))] == y[i]:
            correct += 1
        top_idx = np.argsort(p)[-3:]
        if y[i] in class_index and class_index[y[i]] in top_idx:
            top3 += 1
        if y[i] in class_index:
            ti = class_index[y[i]]
            nll.append(-np.log(max(p[ti], 1e-12)))
            gt = G[ti]
            G_truth.append(float(gt) if np.isfinite(gt) else 50.0)
            if with_efe_components and np.isfinite(gt):
                risks.append(float(comp["risk"][ti]))
                ambs.append(float(comp["ambiguity"][ti]))
                habs.append(float(comp["habit"][ti]))
        else:
            nll.append(12.0)
            G_truth.append(50.0)

    out = {
        "n": int(len(framed)),
        "accuracy": float(correct / len(framed)),
        "top3_accuracy": float(top3 / len(framed)),
        "cross_entropy": float(np.mean(nll)),
        "mean_G_truth": float(np.mean(G_truth)) if G_truth else float("nan"),
    }
    if with_efe_components:
        out["mean_risk"] = float(np.mean(risks)) if risks else float("nan")
        out["mean_ambiguity"] = float(np.mean(ambs)) if ambs else float("nan")
        out["mean_habit"] = float(np.mean(habs)) if habs else float("nan")
    return out


def apply_fep_config(bundle: FEPPolicyBundle, cfg: FEPConfig) -> FEPPolicyBundle:
    from copy import copy

    b = copy(bundle)
    b.fep_cfg = cfg
    b.policy_kind = f"fep_{cfg.mode}"
    b._cache_pi = {}
    b._cache_G = {}
    b.train_metrics = dict(bundle.train_metrics)
    return b


def tune_fep_on_fit(
    bundle: FEPPolicyBundle,
    fit_df: pd.DataFrame,
    grid: list[FEPConfig],
    eval_max_rows: int = 25000,
) -> tuple[FEPPolicyBundle, list[dict]]:
    rows = []
    best: FEPPolicyBundle | None = None
    best_acc = -1.0
    for cfg in grid:
        cand = apply_fep_config(bundle, cfg)
        ns = next_step_accuracy_fep(cand, fit_df, max_rows=eval_max_rows)
        row = {
            "mode": cfg.mode,
            "gamma": cfg.gamma_precision,
            "risk_w": cfg.risk_weight,
            "amb_w": cfg.ambiguity_weight,
            "habit_w": cfg.habit_weight,
            "fit_acc": ns["accuracy"],
            "fit_top3": ns["top3_accuracy"],
            "fit_ce": ns["cross_entropy"],
            "n_eval": ns["n"],
        }
        rows.append(row)
        if ns["accuracy"] > best_acc:
            best_acc = ns["accuracy"]
            best = cand
    assert best is not None
    best.train_metrics = dict(bundle.train_metrics)
    best.train_metrics["tune_grid"] = rows
    best.train_metrics["tune_selected"] = {
        "mode": best.fep_cfg.mode,
        "gamma": best.fep_cfg.gamma_precision,
        "risk_w": best.fep_cfg.risk_weight,
        "amb_w": best.fep_cfg.ambiguity_weight,
        "habit_w": best.fep_cfg.habit_weight,
        "fit_acc": best_acc,
    }
    return best, rows


def default_fep_tune_grid() -> list[FEPConfig]:
    base = dict(dirichlet_alpha=0.5, preference_power=1.0, empty_transition_entropy=3.0)
    grid: list[FEPConfig] = []
    for g in (1.0, 2.0, 4.0, 8.0):
        grid.append(
            FEPConfig(
                mode="habit_only",
                gamma_precision=g,
                habit_weight=1.0,
                risk_weight=0.0,
                ambiguity_weight=0.0,
                **base,
            )
        )
    for g in (2.0, 4.0):
        for wr, wa, wh in ((0.25, 0.25, 1.0), (0.5, 0.5, 1.0), (1.0, 0.25, 1.0), (0.25, 1.0, 1.0)):
            grid.append(
                FEPConfig(
                    mode="full_efe",
                    gamma_precision=g,
                    risk_weight=wr,
                    ambiguity_weight=wa,
                    habit_weight=wh,
                    **base,
                )
            )
    return grid


def train_fep_policies(
    fit_df: pd.DataFrame,
    fep_cfg: FEPConfig | None = None,
    amount_bin_edges: Optional[np.ndarray] = None,
    tune: bool = False,
    tune_grid: list[FEPConfig] | None = None,
    tune_eval_max_rows: int = 25000,
) -> FEPPolicyBundle:
    cfg = fep_cfg or FEPConfig()
    framed, edges = prepare_trace_frame(fit_df, amount_bin_edges=amount_bin_edges)
    agent_to_role = _infer_roles(framed)
    framed["role_id"] = framed["agent"].map(agent_to_role).fillna("UNKNOWN")
    framed = framed.sort_values(["case:concept:name", "time:timestamp"]).copy()
    framed["next_activity"] = framed.groupby("case:concept:name")["concept:name"].shift(-1)
    framed["next_activity"] = framed["next_activity"].fillna(framed["concept:name"]).astype(str)

    action_classes = sorted(framed["action"].astype(str).unique().tolist())
    outcome_classes = sorted(framed["next_activity"].astype(str).unique().tolist())
    a_index = {a: i for i, a in enumerate(action_classes)}
    o_index = {o: i for i, o in enumerate(outcome_classes)}
    n_a, n_o = len(action_classes), len(outcome_classes)

    role_action_mask: dict[str, np.ndarray] = {}
    for role, g in framed.groupby("role_id"):
        mask = np.zeros(n_a, dtype=bool)
        for a in g["action"].astype(str).unique():
            if a in a_index:
                mask[a_index[a]] = True
        role_action_mask[str(role)] = mask

    habit_by_agent: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_a))
    habit_by_role: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_a))
    habit_global: dict[tuple[str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_a))
    trans_by_agent: dict[tuple[str, str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_o))
    trans_by_ctx: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_o))
    C_ctx_counts: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_o))
    C_role_counts: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n_o))

    for prev, abin, agent, role, act, nxt in zip(
        framed["prev_activity"].astype(str),
        framed["amount_bin"].astype(str),
        framed["agent"].astype(str),
        framed["role_id"].astype(str),
        framed["action"].astype(str),
        framed["next_activity"].astype(str),
    ):
        ai = a_index[act]
        oi = o_index[nxt]
        habit_by_agent[(prev, abin, agent)][ai] += 1.0
        habit_by_role[(prev, abin, role)][ai] += 1.0
        habit_global[(prev, abin)][ai] += 1.0
        trans_by_agent[(prev, abin, agent, act)][oi] += 1.0
        trans_by_ctx[(prev, abin, act)][oi] += 1.0
        C_ctx_counts[(prev, abin, role)][oi] += 1.0
        C_role_counts[role][oi] += 1.0

    alpha = cfg.dirichlet_alpha
    pow_ = cfg.preference_power
    ln_C_by_ctx = {}
    for k, counts in C_ctx_counts.items():
        p = _dirichlet_mean(np.power(counts, pow_), alpha)
        ln_C_by_ctx[k] = np.log(np.clip(p, 1e-12, 1.0))
    ln_C_by_role = {}
    for role, counts in C_role_counts.items():
        p = _dirichlet_mean(np.power(counts, pow_), alpha)
        ln_C_by_role[role] = np.log(np.clip(p, 1e-12, 1.0))

    latency: dict[tuple[str, str], float] = {}
    framed["dt"] = framed.groupby("case:concept:name")["time:timestamp"].diff().dt.total_seconds()
    for (agent, act), g in framed.dropna(subset=["dt"]).groupby(["agent", "action"]):
        med = float(g["dt"].median())
        if np.isfinite(med) and med > 0:
            latency[(str(agent), str(act))] = med

    handover_probs: dict[str, dict[str, float]] = {}
    seq = framed[["case:concept:name", "agent"]].copy()
    seq["next_agent"] = seq.groupby("case:concept:name")["agent"].shift(-1)
    for a, g in seq.dropna(subset=["next_agent"]).groupby("agent"):
        dests = g["next_agent"].astype(str).value_counts().to_dict()
        s = float(sum(dests.values()))
        stay = s
        probs = {b: c / (s + stay) for b, c in dests.items()}
        probs[str(a)] = stay / (s + stay)
        handover_probs[str(a)] = probs

    bundle = FEPPolicyBundle(
        action_classes=action_classes,
        role_action_mask=role_action_mask,
        agent_to_role=agent_to_role,
        latency_sec=latency,
        handover_probs=handover_probs,
        amount_bin_edges=edges,
        outcome_classes=outcome_classes,
        ln_C_by_ctx=ln_C_by_ctx,
        ln_C_by_role=ln_C_by_role,
        habit_by_agent=dict(habit_by_agent),
        habit_by_role=dict(habit_by_role),
        habit_global=dict(habit_global),
        trans_by_agent=dict(trans_by_agent),
        trans_by_ctx=dict(trans_by_ctx),
        fep_cfg=cfg,
        policy_kind=f"fep_{cfg.mode}",
    )

    if tune:
        bundle, _ = tune_fep_on_fit(
            bundle, fit_df, tune_grid or default_fep_tune_grid(), eval_max_rows=tune_eval_max_rows
        )
        cfg = bundle.fep_cfg

    ns = next_step_accuracy_fep(bundle, fit_df, with_efe_components=True, max_rows=40000)
    bundle.train_metrics.update(
        {
            "n_samples": int(len(framed)),
            "n_actions": n_a,
            "n_outcomes": n_o,
            "n_agents": int(framed["agent"].nunique()),
            "n_habit_agent_contexts": len(habit_by_agent),
            "n_habit_role_contexts": len(habit_by_role),
            "n_trans_agent": len(trans_by_agent),
            "n_trans_ctx": len(trans_by_ctx),
            "fit_action_accuracy": ns["accuracy"],
            "fit_top3_accuracy": ns["top3_accuracy"],
            "generative_cross_entropy": ns["cross_entropy"],
            "variational_free_energy_nats": ns["cross_entropy"],
            "mean_G_truth": ns.get("mean_G_truth"),
            "mean_risk": ns.get("mean_risk"),
            "mean_ambiguity": ns.get("mean_ambiguity"),
            "mean_habit_term": ns.get("mean_habit"),
            "fep_cfg": {
                "mode": cfg.mode,
                "dirichlet_alpha": cfg.dirichlet_alpha,
                "gamma_precision": cfg.gamma_precision,
                "preference_power": cfg.preference_power,
                "habit_weight": cfg.habit_weight,
                "ambiguity_weight": cfg.ambiguity_weight,
                "risk_weight": cfg.risk_weight,
                "empty_transition_entropy": cfg.empty_transition_entropy,
            },
            "parity_fixes": [
                "habit_key=(prev,amount_bin,agent) + backoff role/global",
                "transition backoff agent→ctx",
                "C(o|prev,amount_bin,role)",
                "tune on fit only if tune=True",
            ],
            "loss_form": "G=w_r·KL(q(o'|a)||C)+w_a·H(q)−w_h·ln P_habit; π∝exp(−γG)",
            "note": "0.6: agent-level habit; 0.5 был role-level habit (непаритет с softmax)",
        }
    )
    return bundle
