"""
Политика активного вывода (Friston): минимизация ожидаемой свободной энергии.

Не путать с прокси L≈CE+λH в softmax.py.

Дискретная одношаговая схема (categorical active inference):
  G(a | I, role) = Risk + Ambiguity − Habit
  Risk      = KL( q(o'|I,a) || C(o') )     — отклонение прогноза от предпочтений
  Ambiguity = H( q(o'|I,a) )              — неопределённость исхода после действия
  Habit     = ln P_Dirichlet(a | I, role) — генеративная привычка (не логистика)

Постериор политики (Friston):
  π(a) ∝ exp( −γ · G(a) )  внутри мембраны роли.

Генеративная модель — Dirichlet–Categorical по счётчикам fit (α>0), без sklearn LR.
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
    gamma_precision: float = 2.0  # γ: точность политики (inv. temperature)
    preference_power: float = 1.0  # C ∝ counts^p
    habit_weight: float = 1.0  # вклад −w·ln P_habit в G
    ambiguity_weight: float = 1.0
    risk_weight: float = 1.0
    # сглаживание для пустых (prev,abin,action) транзиций
    empty_transition_entropy: float = 3.0  # nats, штраф «не знаю исход»


@dataclass
class FEPPolicyBundle:
    """Генеративная FEP-политика; duck-compatible с Softmax для сима/timing."""

    action_classes: list[str]
    role_action_mask: dict[str, np.ndarray]
    agent_to_role: dict[str, str]
    latency_sec: dict[tuple[str, str], float]
    handover_probs: dict[str, dict[str, float]]
    amount_bin_edges: Optional[np.ndarray]
    train_metrics: dict = field(default_factory=dict)
    policy_kind: str = "fep_efe"
    fep_cfg: FEPConfig = field(default_factory=FEPConfig)
    # outcome vocabulary (next concept:name)
    outcome_classes: list[str] = field(default_factory=list)
    # ln C(o) — предпочтения по исходам (роль → вектор |outcomes|)
    ln_C_by_role: dict[str, np.ndarray] = field(default_factory=dict)
    # habit counts: (prev, abin, role) → vector |actions| (сырые + уже с α в mean)
    habit_counts: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    # transition counts: (prev, abin, action) → vector |outcomes|
    transition_counts: dict[tuple[str, str, str], np.ndarray] = field(default_factory=dict)
    # кэш π / G по контексту (prev, abin, role)
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
        return np.ones_like(p) / len(p)
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


def train_fep_policies(
    fit_df: pd.DataFrame,
    fep_cfg: FEPConfig | None = None,
    amount_bin_edges: Optional[np.ndarray] = None,
) -> FEPPolicyBundle:
    """
    Обучение генеративной модели + предпочтений C на fit.
    Softmax/LR здесь нет — только счётчики + Dirichlet.
    """
    cfg = fep_cfg or FEPConfig()
    framed, edges = prepare_trace_frame(fit_df, amount_bin_edges=amount_bin_edges)
    agent_to_role = _infer_roles(framed)
    framed["role_id"] = framed["agent"].map(agent_to_role).fillna("UNKNOWN")
    framed = framed.sort_values(["case:concept:name", "time:timestamp"]).copy()
    framed["next_activity"] = framed.groupby("case:concept:name")["concept:name"].shift(-1)
    # последний шаг кейса: исход = текущая activity (терминал/хвост)
    framed["next_activity"] = framed["next_activity"].fillna(framed["concept:name"]).astype(str)

    action_classes = sorted(framed["action"].astype(str).unique().tolist())
    outcome_classes = sorted(framed["next_activity"].astype(str).unique().tolist())
    a_index = {a: i for i, a in enumerate(action_classes)}
    o_index = {o: i for i, o in enumerate(outcome_classes)}
    n_a, n_o = len(action_classes), len(outcome_classes)

    # мембраны ролей
    role_action_mask: dict[str, np.ndarray] = {}
    for role, g in framed.groupby("role_id"):
        mask = np.zeros(n_a, dtype=bool)
        for a in g["action"].astype(str).unique():
            if a in a_index:
                mask[a_index[a]] = True
        role_action_mask[str(role)] = mask

    # habit counts
    habit_raw: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_a))
    for prev, abin, role, act in zip(
        framed["prev_activity"].astype(str),
        framed["amount_bin"].astype(str),
        framed["role_id"].astype(str),
        framed["action"].astype(str),
    ):
        habit_raw[(prev, abin, role)][a_index[act]] += 1.0

    # transitions (prev, abin, action) → next activity
    trans_raw: dict[tuple[str, str, str], np.ndarray] = defaultdict(lambda: np.zeros(n_o))
    for prev, abin, act, nxt in zip(
        framed["prev_activity"].astype(str),
        framed["amount_bin"].astype(str),
        framed["action"].astype(str),
        framed["next_activity"].astype(str),
    ):
        trans_raw[(prev, abin, act)][o_index[nxt]] += 1.0

    # предпочтения C(o|role): частота next_activity^power
    ln_C_by_role: dict[str, np.ndarray] = {}
    for role, g in framed.groupby("role_id"):
        counts = np.zeros(n_o)
        for o, c in g["next_activity"].value_counts().items():
            counts[o_index[str(o)]] = float(c) ** cfg.preference_power
        p = _dirichlet_mean(counts, cfg.dirichlet_alpha)
        ln_C_by_role[str(role)] = np.log(np.clip(p, 1e-12, 1.0))

    # latency + handover — как в softmax (общая инфраструктура сима)
    latency: dict[tuple[str, str], float] = {}
    for (agent, act), g in framed.groupby(["agent", "action"]):
        # медиана dt до события нет → используем 1h default later; здесь счётчик частоты как proxy
        latency[(str(agent), str(act))] = 3600.0
    # уточним latency по dt если есть
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

    habit_counts = {k: v.copy() for k, v in habit_raw.items()}
    transition_counts = {k: v.copy() for k, v in trans_raw.items()}

    bundle = FEPPolicyBundle(
        action_classes=action_classes,
        role_action_mask=role_action_mask,
        agent_to_role=agent_to_role,
        latency_sec=latency,
        handover_probs=handover_probs,
        amount_bin_edges=edges,
        outcome_classes=outcome_classes,
        ln_C_by_role=ln_C_by_role,
        habit_counts=habit_counts,
        transition_counts=transition_counts,
        fep_cfg=cfg,
        policy_kind="fep_efe",
    )

    # метрики fit (один проход с кэшем G по уникальным контекстам)
    ns = next_step_accuracy_fep(bundle, fit_df, with_efe_components=True)
    gen_ce = float(ns["cross_entropy"])
    free_energy = gen_ce

    bundle.train_metrics = {
        "n_samples": int(len(framed)),
        "n_actions": n_a,
        "n_outcomes": n_o,
        "n_agents": int(framed["agent"].nunique()),
        "n_habit_contexts": len(habit_counts),
        "n_transition_contexts": len(transition_counts),
        "fit_action_accuracy": ns["accuracy"],
        "fit_top3_accuracy": ns["top3_accuracy"],
        "generative_cross_entropy": gen_ce,
        "variational_free_energy_nats": free_energy,
        "mean_G_truth": ns.get("mean_G_truth"),
        "mean_G_min": ns.get("mean_G_min"),
        "mean_risk": ns.get("mean_risk"),
        "mean_ambiguity": ns.get("mean_ambiguity"),
        "mean_habit_term": ns.get("mean_habit"),
        "fep_cfg": {
            "dirichlet_alpha": cfg.dirichlet_alpha,
            "gamma_precision": cfg.gamma_precision,
            "preference_power": cfg.preference_power,
            "habit_weight": cfg.habit_weight,
            "ambiguity_weight": cfg.ambiguity_weight,
            "risk_weight": cfg.risk_weight,
            "empty_transition_entropy": cfg.empty_transition_entropy,
        },
        "loss_form": "G=w_r·KL(q(o'|a)||C)+w_a·H(q)−w_h·ln P_habit; π∝exp(−γG)",
        "note": "FEP/EFE — не softmax LR; CE+λH из 0.2–0.4 был только прокси",
    }
    return bundle


def expected_free_energy(
    bundle: FEPPolicyBundle,
    prev: str,
    amount_bin: str,
    role: str,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """
    Вектор G(a) и компоненты для всех action_classes.
    Недопустимые по мембране → +inf. Кэш по (prev, abin, role).
    """
    cache_key = (str(prev), str(amount_bin), str(role))
    if cache_key in bundle._cache_G:
        return bundle._cache_G[cache_key]

    cfg = bundle.fep_cfg
    n_a = len(bundle.action_classes)
    G = np.full(n_a, np.inf, dtype=float)
    risk_v = np.zeros(n_a)
    amb_v = np.zeros(n_a)
    hab_v = np.zeros(n_a)

    mask = bundle.role_action_mask.get(role)
    if mask is None:
        mask = np.ones(n_a, dtype=bool)

    ln_C = bundle.ln_C_by_role.get(role)
    if ln_C is None:
        ln_C = -np.log(len(bundle.outcome_classes)) * np.ones(len(bundle.outcome_classes))

    C = np.exp(ln_C)
    C = C / C.sum()

    habit_key = cache_key
    habit_counts = bundle.habit_counts.get(habit_key)
    if habit_counts is None:
        habit_p = np.ones(n_a) / n_a
    else:
        habit_p = _dirichlet_mean(habit_counts, cfg.dirichlet_alpha)

    n_o = len(bundle.outcome_classes)
    uniform_q = np.ones(n_o) / max(n_o, 1)
    empty_risk = _kl(uniform_q, C)

    for i, act in enumerate(bundle.action_classes):
        if not mask[i]:
            continue
        tkey = (str(prev), str(amount_bin), act)
        tc = bundle.transition_counts.get(tkey)
        if tc is None or tc.sum() <= 0:
            amb = cfg.empty_transition_entropy
            risk = empty_risk
        else:
            q = _dirichlet_mean(tc, cfg.dirichlet_alpha)
            amb = _entropy(q)
            risk = _kl(q, C)

        habit = float(np.log(max(habit_p[i], 1e-12)))
        risk_v[i] = risk
        amb_v[i] = amb
        hab_v[i] = habit
        G[i] = (
            cfg.risk_weight * risk
            + cfg.ambiguity_weight * amb
            - cfg.habit_weight * habit
        )

    comps = {"risk": risk_v, "ambiguity": amb_v, "habit": hab_v}
    bundle._cache_G[cache_key] = (G, comps)
    return G, comps


def policy_proba_fep(
    bundle: FEPPolicyBundle,
    prev: str,
    amount_bin: str,
    agent: str,
) -> np.ndarray:
    """π(a) ∝ exp(−γ G(a)), мембрана уже в G=+inf."""
    role = bundle.agent_to_role.get(str(agent), "UNKNOWN")
    cache_key = (str(prev), str(amount_bin), role)
    if cache_key in bundle._cache_pi:
        return bundle._cache_pi[cache_key]

    G, _ = expected_free_energy(bundle, str(prev), str(amount_bin), role)
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
) -> dict:
    framed, _ = prepare_trace_frame(df, amount_bin_edges=bundle.amount_bin_edges)
    known = framed["agent"].isin(bundle.agent_to_role)
    framed = framed[known]
    if framed.empty:
        return {
            "n": 0,
            "accuracy": float("nan"),
            "top3_accuracy": float("nan"),
            "cross_entropy": float("nan"),
            "mean_G_truth": float("nan"),
        }

    class_index = {c: i for i, c in enumerate(bundle.action_classes)}
    roles = framed["agent"].map(bundle.agent_to_role).astype(str).to_numpy()
    prevs = framed["prev_activity"].astype(str).to_numpy()
    abins = framed["amount_bin"].astype(str).to_numpy()
    y = framed["action"].astype(str).to_numpy()

    correct = 0
    top3 = 0
    nll = []
    G_truth = []
    G_min = []
    risks = []
    ambs = []
    habs = []

    for i in range(len(framed)):
        agent = str(framed["agent"].iloc[i])
        prev, abin, role = prevs[i], abins[i], roles[i]
        p = policy_proba_fep(bundle, prev, abin, agent)
        G, comp = expected_free_energy(bundle, prev, abin, role)
        pred_i = int(np.argmax(p))
        if bundle.action_classes[pred_i] == y[i]:
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
        finite = G[np.isfinite(G)]
        G_min.append(float(np.min(finite)) if len(finite) else float("nan"))

    out = {
        "n": int(len(framed)),
        "accuracy": float(correct / len(framed)),
        "top3_accuracy": float(top3 / len(framed)),
        "cross_entropy": float(np.mean(nll)),
        "mean_G_truth": float(np.mean(G_truth)) if G_truth else float("nan"),
        "mean_G_min": float(np.nanmean(G_min)) if G_min else float("nan"),
    }
    if with_efe_components:
        out["mean_risk"] = float(np.mean(risks)) if risks else float("nan")
        out["mean_ambiguity"] = float(np.mean(ambs)) if ambs else float("nan")
        out["mean_habit"] = float(np.mean(habs)) if habs else float("nan")
    return out


def clear_fep_caches(bundle: FEPPolicyBundle) -> None:
    bundle._cache_pi.clear()
    bundle._cache_G.clear()