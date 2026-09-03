"""Сравнение симуляции с holdout + метрики политики (softmax или FEP)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np
import pandas as pd

from orgtwin.policy.fep import FEPPolicyBundle, next_step_accuracy_fep
from orgtwin.policy.softmax import SoftmaxPolicyBundle, action_names_vectorized, next_step_accuracy
from orgtwin.sim.engine import SimResult

PolicyBundle = Union[SoftmaxPolicyBundle, FEPPolicyBundle]


@dataclass
class EvalReport:
    metrics: dict
    weekly_actual: pd.Series
    weekly_pred: pd.Series


def _weekly_event_counts_from_ts(ts: pd.Series) -> pd.Series:
    ts = pd.to_datetime(ts, utc=True).dt.tz_localize(None)
    return ts.dt.to_period("W").value_counts().sort_index()


def actual_case_durations(df: pd.DataFrame) -> dict[str, float]:
    g = df.groupby("case:concept:name")["time:timestamp"]
    dur = (g.max() - g.min()).dt.total_seconds()
    return dur.to_dict()


def evaluate(
    hold: pd.DataFrame,
    sim: SimResult,
    policy: PolicyBundle | None = None,
) -> EvalReport:
    weekly_a = _weekly_event_counts_from_ts(hold["time:timestamp"])

    if sim.events:
        sim_ts = pd.Series([e["time:timestamp"] for e in sim.events])
        weekly_p = _weekly_event_counts_from_ts(sim_ts)
    else:
        weekly_p = pd.Series(dtype=float)

    idx = weekly_a.index.union(weekly_p.index)
    a = weekly_a.reindex(idx, fill_value=0).astype(float)
    p = weekly_p.reindex(idx, fill_value=0).astype(float)
    mape = float(np.mean(np.abs(a - p) / np.maximum(a, 1.0)))
    mae = float(np.mean(np.abs(a - p)))
    corr = float(a.corr(p)) if len(a) > 1 and a.std() > 0 and p.std() > 0 else float("nan")

    actual_dur = actual_case_durations(hold)
    common = [c for c in sim.case_durations_sec if c in actual_dur]
    if common:
        ad = np.array([actual_dur[c] for c in common], dtype=float)
        pd_ = np.array([sim.case_durations_sec[c] for c in common], dtype=float)
        dur_mae = float(np.mean(np.abs(np.log1p(ad) - np.log1p(pd_))))
        dur_spearman = float(pd.Series(ad).corr(pd.Series(pd_), method="spearman"))
    else:
        dur_mae = float("nan")
        dur_spearman = float("nan")

    hold_actions = action_names_vectorized(hold).value_counts().head(20)
    pred_actions = pd.Series(sim.action_counts).sort_values(ascending=False).head(20)
    overlap = len(set(hold_actions.index) & set(pred_actions.index))

    def terminal_share(actions: pd.Series) -> dict:
        out = {}
        for pref in ("A_CANCELLED", "A_DECLINED", "A_APPROVED", "A_REGISTERED"):
            out[pref] = float(actions.astype(str).str.startswith(pref).mean())
        return out

    actual_term = terminal_share(action_names_vectorized(hold))
    if sim.action_counts:
        sim_act = pd.Series(
            np.repeat(list(sim.action_counts.keys()), list(sim.action_counts.values()))
        )
        pred_term = terminal_share(sim_act)
    else:
        pred_term = {k: 0.0 for k in actual_term}

    metrics = {
        "weekly_events_mae": mae,
        "weekly_events_mape": mape,
        "weekly_events_corr": corr,
        "case_duration_log_mae": dur_mae,
        "case_duration_spearman": dur_spearman,
        "n_cases_compared": len(common),
        "top20_action_overlap": overlap,
        "sim_events": len(sim.events),
        "hold_events": int(len(hold)),
        "terminal_share_actual": actual_term,
        "terminal_share_pred": pred_term,
    }

    if policy is not None:
        if getattr(policy, "policy_kind", "softmax") == "fep_efe":
            ns = next_step_accuracy_fep(policy, hold)  # type: ignore[arg-type]
            metrics["holdout_next_step_accuracy"] = ns["accuracy"]
            metrics["holdout_next_step_top3"] = ns["top3_accuracy"]
            metrics["holdout_next_step_ce"] = ns["cross_entropy"]
            metrics["holdout_next_step_n"] = ns["n"]
            metrics["holdout_mean_G_truth"] = ns.get("mean_G_truth")
            metrics["holdout_variational_FE"] = ns["cross_entropy"]  # q=δ(role)
            metrics["policy_kind"] = "fep_efe"
        else:
            ns = next_step_accuracy(policy, hold)  # type: ignore[arg-type]
            metrics["holdout_next_step_accuracy"] = ns["accuracy"]
            metrics["holdout_next_step_top3"] = ns["top3_accuracy"]
            metrics["holdout_next_step_ce"] = ns["cross_entropy"]
            metrics["holdout_next_step_n"] = ns["n"]
            lam = float(policy.train_metrics.get("lambda_entropy", 0.05))
            metrics["holdout_free_energy_proxy"] = float(
                ns["cross_entropy"] + lam * policy.train_metrics.get("policy_entropy_nats", 0.0)
            )
            metrics["policy_kind"] = "softmax"

    return EvalReport(metrics=metrics, weekly_actual=a, weekly_pred=p)
