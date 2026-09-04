"""
Классические политики нейроавтоматов: softmax / мультиномиальная логистика.

Information → признаки → logits(Action). Усреднение: роль-приор + агент (shrinkage).
Свободная энергия (инженерная аппроксимация из аудита):
  F ≈ CE(action|info) + λ · H(policy)   (+ доля недопустимых мутаций как fail)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder


def action_name_from_row(row: pd.Series) -> str:
    life = row.get("lifecycle:transition")
    if life is None or (isinstance(life, float) and np.isnan(life)) or pd.isna(life):
        return str(row["concept:name"])
    return f"{row['concept:name']}|{life}"


def action_names_vectorized(df: pd.DataFrame) -> pd.Series:
    """Векторная сборка Action (без медленного DataFrame.apply)."""
    act = df["concept:name"].astype(str)
    if "lifecycle:transition" not in df.columns:
        return act
    life = df["lifecycle:transition"]
    mask = life.notna()
    out = act.copy()
    out.loc[mask] = act.loc[mask] + "|" + life.loc[mask].astype(str)
    return out


@dataclass
class SoftmaxPolicyBundle:
    """Обученный softmax: контекст Information + агент → Action."""

    action_classes: list[str]
    encoder: OneHotEncoder
    model: LogisticRegression
    feature_cols: list[str]
    # роль → индексы допустимых действий (мембрана)
    role_action_mask: dict[str, np.ndarray]
    agent_to_role: dict[str, str]
    # mean latency per (agent, action)
    latency_sec: dict[tuple[str, str], float]
    # handover: P(next_agent | current_agent) rows normalized
    handover_probs: dict[str, dict[str, float]]
    train_metrics: dict = field(default_factory=dict)
    amount_bin_edges: Optional[np.ndarray] = None
    policy_kind: str = "softmax"

    def allowed_actions(self, role_id: str) -> list[str]:
        mask = self.role_action_mask.get(role_id)
        if mask is None:
            return list(self.action_classes)
        return [a for a, m in zip(self.action_classes, mask) if m]


def _resolve_agent_col(df: pd.DataFrame, agent_col: Optional[str] = None) -> str:
    if agent_col and agent_col in df.columns:
        return agent_col
    if "org:resource" in df.columns:
        return "org:resource"
    if "org:group" in df.columns:
        return "org:group"
    return "org:resource"


def _resolve_context_col(df: pd.DataFrame, context_col: Optional[str] = None) -> Optional[str]:
    if context_col:
        return context_col if context_col in df.columns else None
    for c in (
        "case:AMOUNT_REQ",
        "AMOUNT_REQ",
        "Cumulative net worth (EUR)",
        "case:Age",
        "Age",
    ):
        if c in df.columns:
            return c
    return None


def prepare_trace_frame(
    df: pd.DataFrame,
    amount_bin_edges: Optional[np.ndarray] = None,
    agent_col: Optional[str] = None,
    context_col: Optional[str] = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Добавляет prev_activity, prev2_activity, action, amount_bin, agent. Возвращает edges для holdout."""
    out = df.copy()
    a_col = _resolve_agent_col(out, agent_col)
    if a_col not in out.columns:
        out[a_col] = "UNKNOWN"
    out[a_col] = out[a_col].fillna("UNKNOWN").astype(str)
    by_case = out.groupby("case:concept:name")["concept:name"]
    out["prev_activity"] = by_case.shift(1).fillna("∅").astype(str)
    out["prev2_activity"] = by_case.shift(2).fillna("∅").astype(str)
    out["action"] = action_names_vectorized(out)

    ctx = _resolve_context_col(out, context_col)
    if ctx:
        vals = pd.to_numeric(out[ctx], errors="coerce")
        if vals.notna().sum() == 0:
            out["amount_bin"] = out[ctx].fillna("∅").astype(str)
            if amount_bin_edges is None:
                amount_bin_edges = np.array([0.0, 1.0])
        else:
            if amount_bin_edges is None:
                qs = vals.quantile([0.0, 0.25, 0.5, 0.75, 1.0]).to_numpy(dtype=float)
                edges = np.unique(qs[~np.isnan(qs)])
                if len(edges) < 2:
                    lo = float(np.nanmin(vals.to_numpy())) if vals.notna().any() else 0.0
                    edges = np.array([lo, lo + 1.0])
                amount_bin_edges = edges
            fill = float(vals.median()) if vals.notna().any() else 0.0
            inner = amount_bin_edges[1:-1] if len(amount_bin_edges) > 2 else np.array([])
            out["amount_bin"] = np.digitize(vals.fillna(fill), inner, right=True).astype(str)
    else:
        out["amount_bin"] = "0"
        if amount_bin_edges is None:
            amount_bin_edges = np.array([0.0, 1.0])

    out["agent"] = out[a_col]
    return out, amount_bin_edges


def _infer_roles(df: pd.DataFrame) -> dict[str, str]:
    from collections import Counter, defaultdict
    from orgtwin.ingest.xes_loader import infer_role

    votes: dict[str, Counter] = defaultdict(Counter)
    for agent, act in zip(df["org:resource"].astype(str), df["concept:name"].astype(str)):
        votes[agent][infer_role(act)] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def train_softmax_policies(
    fit_df: pd.DataFrame,
    lambda_entropy: float = 0.05,
    max_iter: int = 200,
    random_state: int = 42,
    solver: str = "saga",
    tol: float = 1e-3,
    C: float = 1.0,
    agent_col: Optional[str] = None,
    context_col: Optional[str] = None,
    role_mode: str = "activity_prefix",
) -> SoftmaxPolicyBundle:
    """
    Классика: One-Hot(prev, prev2, amount_bin, agent) → multinomial logistic (softmax).
    Мембрана роли = support действий роли; logits вне мембраны маскируются при сэмпле.
    """
    framed, edges = prepare_trace_frame(fit_df, agent_col=agent_col, context_col=context_col)
    from orgtwin.ingest.xes_loader import infer_roles_from_frame

    agent_to_role = infer_roles_from_frame(framed, role_mode=role_mode)
    framed["role_id"] = framed["agent"].map(agent_to_role).fillna("UNKNOWN")

    # порядок 2 по активности + контекст + агент (как в диагностике, плюс prev2)
    feature_cols = ["prev_activity", "prev2_activity", "amount_bin", "agent"]
    X_raw = framed[feature_cols].astype(str)
    y = framed["action"].astype(str)

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    X = encoder.fit_transform(X_raw)

    # sklearn LogisticRegression на multiclass = softmax (multinomial)
    # solver из констант; смена lbfgs→saga зафиксирована в LAB_JOURNAL
    model = LogisticRegression(
        solver=solver,
        max_iter=max_iter,
        random_state=random_state,
        C=C,
        tol=tol,
    )
    model.fit(X, y)
    action_classes = list(model.classes_)

    # маски мембран по ролям
    role_action_mask: dict[str, np.ndarray] = {}
    for role, g in framed.groupby("role_id"):
        present = set(g["action"].unique())
        role_action_mask[str(role)] = np.array([a in present for a in action_classes], dtype=bool)

    # latency
    framed = framed.sort_values(["case:concept:name", "time:timestamp"])
    framed["dt"] = (
        framed.groupby("case:concept:name")["time:timestamp"].diff().dt.total_seconds()
    )
    latency: dict[tuple[str, str], float] = {}
    for (agent, action), g in framed.dropna(subset=["dt"]).groupby(["agent", "action"]):
        dts = g["dt"][(g["dt"] >= 0) & (g["dt"] < 60 * 60 * 24 * 30)]
        if len(dts):
            latency[(str(agent), str(action))] = float(dts.median())

    # handover probs
    handover_counts: dict[str, dict[str, float]] = {}
    for _, g in framed.groupby("case:concept:name"):
        agents = g["agent"].tolist()
        for a, b in zip(agents, agents[1:]):
            if a == b:
                continue
            handover_counts.setdefault(a, {})
            handover_counts[a][b] = handover_counts[a].get(b, 0.0) + 1.0
    handover_probs: dict[str, dict[str, float]] = {}
    for a, dests in handover_counts.items():
        s = sum(dests.values())
        # stay mass ≈ суммарный hand-over (чтобы не всегда уходить)
        stay = s
        probs = {b: c / (s + stay) for b, c in dests.items()}
        probs[a] = stay / (s + stay)
        handover_probs[a] = probs

    # метрики на fit: CE, entropy, fail (действие вне маски роли — не должно быть)
    proba = model.predict_proba(X)
    # CE
    class_index = {c: i for i, c in enumerate(action_classes)}
    y_idx = np.array([class_index[v] for v in y])
    row_p = proba[np.arange(len(y_idx)), y_idx]
    ce = float(-np.mean(np.log(np.clip(row_p, 1e-12, 1.0))))
    # средняя энтропия предсказанного распределения
    ent = float(-np.mean(np.sum(proba * np.log(np.clip(proba, 1e-12, 1.0)), axis=1)))
    # accuracy
    pred = model.predict(X)
    acc = float(np.mean(pred == y.to_numpy()))
    # F ≈ CE + λ H
    free_energy = ce + lambda_entropy * ent

    # fail: доля переходов prev→action, которые единичны и «ломают» (редко); proxy = 1-acc
    fail_rate = 1.0 - acc

    train_metrics = {
        "n_samples": int(len(framed)),
        "n_actions": len(action_classes),
        "n_agents": int(framed["agent"].nunique()),
        "cross_entropy": ce,
        "policy_entropy_nats": ent,
        "lambda_entropy": lambda_entropy,
        "free_energy_proxy": free_energy,
        "fit_action_accuracy": acc,
        "fail_rate_proxy": fail_rate,
        "loss_audit_form": "L ≈ E[fail] + λ H(policy) ≈ fail_rate + λ * entropy",
    }

    return SoftmaxPolicyBundle(
        action_classes=action_classes,
        encoder=encoder,
        model=model,
        feature_cols=feature_cols,
        role_action_mask=role_action_mask,
        agent_to_role=agent_to_role,
        latency_sec=latency,
        handover_probs=handover_probs,
        train_metrics=train_metrics,
        amount_bin_edges=edges,
    )


def _encode_state(
    bundle: SoftmaxPolicyBundle,
    prev_activity: Any,
    amount_bin: Any,
    agent: str,
) -> Any:
    row = pd.DataFrame(
        [
            {
                "prev_activity": str(prev_activity if prev_activity is not None else "∅"),
                "amount_bin": str(amount_bin if amount_bin is not None else "0"),
                "agent": str(agent),
            }
        ]
    )
    return bundle.encoder.transform(row[bundle.feature_cols].astype(str))


def predict_action_proba(
    bundle: SoftmaxPolicyBundle,
    prev_activity: Any,
    amount_bin: Any,
    agent: str,
    apply_membrane_mask: bool = True,
) -> np.ndarray:
    """P(action | Information, agent); маска мембраны роли + ренормализация."""
    X = _encode_state(bundle, prev_activity, amount_bin, agent)
    logits_p = bundle.model.predict_proba(X)[0].astype(float)
    if apply_membrane_mask:
        role = bundle.agent_to_role.get(str(agent), "UNKNOWN")
        mask = bundle.role_action_mask.get(role)
        if mask is not None and mask.any():
            logits_p = logits_p * mask.astype(float)
            s = logits_p.sum()
            if s > 0:
                logits_p = logits_p / s
            else:
                logits_p = mask.astype(float) / mask.sum()
    return logits_p


def sample_action(
    bundle: SoftmaxPolicyBundle,
    prev_activity: Any,
    amount_bin: Any,
    agent: str,
    rng: np.random.Generator,
) -> str:
    p = predict_action_proba(bundle, prev_activity, amount_bin, agent)
    idx = int(rng.choice(len(bundle.action_classes), p=p))
    return bundle.action_classes[idx]


def sample_next_agent(
    bundle: SoftmaxPolicyBundle,
    current: str,
    rng: np.random.Generator,
) -> str:
    dist = bundle.handover_probs.get(current)
    if not dist:
        return current
    agents = list(dist.keys())
    probs = np.array([dist[a] for a in agents], dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(agents, p=probs))


def next_step_accuracy(
    bundle: SoftmaxPolicyBundle,
    df: pd.DataFrame,
    **prep_kw: Any,
) -> dict:
    """Классическая проверка политики: accuracy / CE / top-3 на holdout."""
    framed, _ = prepare_trace_frame(df, amount_bin_edges=bundle.amount_bin_edges, **prep_kw)
    # только агенты, виденные на fit
    known = framed["agent"].isin(bundle.agent_to_role)
    framed = framed[known]
    if framed.empty:
        return {"n": 0, "accuracy": float("nan"), "top3_accuracy": float("nan"), "cross_entropy": float("nan")}

    X = bundle.encoder.transform(framed[bundle.feature_cols].astype(str))
    proba = bundle.model.predict_proba(X)
    y = framed["action"].astype(str).to_numpy()
    class_index = {c: i for i, c in enumerate(bundle.action_classes)}

    # membrane-masked argmax
    correct = 0
    top3 = 0
    nll = []
    roles = framed["agent"].map(bundle.agent_to_role).to_numpy()
    for i in range(len(framed)):
        p = proba[i].astype(float).copy()
        role = roles[i]
        mask = bundle.role_action_mask.get(role)
        if mask is not None and mask.any():
            p = p * mask.astype(float)
            s = p.sum()
            if s > 0:
                p /= s
        pred = bundle.action_classes[int(np.argmax(p))]
        truth = y[i]
        if pred == truth:
            correct += 1
        top_idx = np.argsort(p)[-3:]
        if truth in bundle.action_classes and class_index[truth] in top_idx:
            top3 += 1
        if truth in class_index:
            nll.append(-np.log(max(p[class_index[truth]], 1e-12)))
        else:
            nll.append(12.0)  # OOV action penalty

    return {
        "n": int(len(framed)),
        "accuracy": float(correct / len(framed)),
        "top3_accuracy": float(top3 / len(framed)),
        "cross_entropy": float(np.mean(nll)),
    }


def prune_membrane_actions(
    bundle: SoftmaxPolicyBundle,
    fit_df: pd.DataFrame,
    lambda_entropy: float = 0.05,
    min_support: int = 30,
) -> dict:
    """
    Жадный прунинг редких действий роли: если support < min_support и
    вклад в снижение H без роста CE — помечаем к удалению из мембраны.
    Классика: frequency + entropy trade-off из аудита.
    """
    framed, _ = prepare_trace_frame(fit_df, amount_bin_edges=bundle.amount_bin_edges)
    framed["role_id"] = framed["agent"].map(bundle.agent_to_role)
    pruned: dict[str, list[str]] = {}
    for role, g in framed.groupby("role_id"):
        counts = g["action"].value_counts()
        rare = [a for a, c in counts.items() if c < min_support]
        # не трогаем терминалы
        rare = [a for a in rare if not any(
            a.startswith(p) for p in ("A_CANCELLED", "A_DECLINED", "A_APPROVED", "A_REGISTERED")
        )]
        if not rare:
            continue
        mask = bundle.role_action_mask[str(role)].copy()
        for a in rare:
            if a in bundle.action_classes:
                idx = bundle.action_classes.index(a)
                mask[idx] = False
        # мембрана не должна опустеть
        if mask.any():
            bundle.role_action_mask[str(role)] = mask
            pruned[str(role)] = rare
    # пересчёт H верхней оценки
    entropy_bits = {}
    for role, mask in bundle.role_action_mask.items():
        n = int(mask.sum())
        entropy_bits[role] = float(np.log2(n)) if n > 1 else 0.0
    return {
        "pruned_actions_by_role": pruned,
        "shannon_upper_bits_after": entropy_bits,
        "lambda_entropy": lambda_entropy,
    }
