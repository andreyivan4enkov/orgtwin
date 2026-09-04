"""Загрузка одного XES-донора → плоский event table."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.conversion.log import converter as log_converter


REQUIRED_COLS = ("case:concept:name", "concept:name", "time:timestamp")


def load_event_table(xes_path: str | Path, agent_col: str | None = None) -> pd.DataFrame:
    path = Path(xes_path)
    if not path.exists():
        raise FileNotFoundError(path)
    log = xes_importer.apply(str(path))
    df = log_converter.apply(log, variant=log_converter.Variants.TO_DATA_FRAME)
    for col in REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"В логе нет колонки {col}")
    df = df.copy()
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"], utc=True)
    resolved = agent_col
    if resolved is None:
        if "org:resource" in df.columns:
            resolved = "org:resource"
        elif "org:group" in df.columns:
            resolved = "org:group"
        else:
            resolved = "org:resource"
            df[resolved] = "UNKNOWN"
    if resolved not in df.columns:
        df[resolved] = "UNKNOWN"
    df[resolved] = df[resolved].fillna("UNKNOWN").astype(str)
    if "org:resource" not in df.columns:
        df["org:resource"] = df[resolved]
    if "lifecycle:transition" not in df.columns:
        df["lifecycle:transition"] = None
    df = df.sort_values(["case:concept:name", "time:timestamp"]).reset_index(drop=True)
    return df


def time_bounds(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    return df["time:timestamp"].min(), df["time:timestamp"].max()


def fit_holdout_split(
    df: pd.DataFrame,
    fit_months: int = 3,
    holdout_months: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Кейс в окне по timestamp первого события.
    fit = [t0, t0+fit_months), holdout = [fit_end, fit_end+holdout_months).
    """
    t0, t1 = time_bounds(df)
    fit_end = t0 + pd.DateOffset(months=fit_months)
    hold_end = fit_end + pd.DateOffset(months=holdout_months)
    case_start = df.groupby("case:concept:name")["time:timestamp"].min()
    fit_cases = case_start[case_start < fit_end].index
    hold_cases = case_start[(case_start >= fit_end) & (case_start < hold_end)].index
    fit = df[df["case:concept:name"].isin(fit_cases)].copy()
    hold = df[df["case:concept:name"].isin(hold_cases)].copy()
    meta = {
        "t0": str(t0),
        "t1": str(t1),
        "fit_end": str(fit_end),
        "hold_end": str(hold_end),
        "fit_cases": int(len(fit_cases)),
        "hold_cases": int(len(hold_cases)),
        "fit_events": int(len(fit)),
        "hold_events": int(len(hold)),
        "fit_months": fit_months,
        "holdout_months": holdout_months,
    }
    return fit, hold, meta


def infer_role(activity: str) -> str:
    """Грубая роль по префиксу активности BPIC 2012 (A_/O_/W_)."""
    if not isinstance(activity, str) or not activity:
        return "UNKNOWN"
    prefix = activity.split("_", 1)[0]
    mapping = {
        "A": "APPLICATION",
        "O": "OFFER",
        "W": "WORKITEM",
    }
    return mapping.get(prefix, prefix)


def infer_role_procurement(activity: str) -> str:
    """Роль по семейству активности BPIC2019 (закупки)."""
    if not isinstance(activity, str) or not activity:
        return "UNKNOWN"
    al = activity.lower()
    if "requisition" in al:
        return "PR"
    if "purchase order" in al or "approval for purchase" in al:
        return "PO"
    if "goods receipt" in al or "service entry" in al:
        return "GR"
    if "invoice" in al or "payment block" in al or "debit memo" in al:
        return "INV"
    if "order confirmation" in al:
        return "CONF"
    if al.startswith("change ") or al.startswith("delete ") or al.startswith("cancel "):
        return "CHANGE"
    return "OTHER"


def filter_event_table(
    df: pd.DataFrame,
    time_from: str | pd.Timestamp | None = None,
    drop_agents: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Отсечь выбросы по времени и/или агентам (NONE, batch_* и т.п.)."""
    out = df
    meta: dict = {}
    if time_from is not None:
        t0 = pd.Timestamp(time_from, tz="UTC")
        case_start = out.groupby("case:concept:name")["time:timestamp"].min()
        keep = case_start[case_start >= t0].index
        out = out[out["case:concept:name"].isin(keep)].copy()
        meta["time_from"] = str(t0)
        meta["cases_after_time_filter"] = int(len(keep))
        meta["events_after_time_filter"] = int(len(out))
    if drop_agents:
        agent_col = "org:resource" if "org:resource" in out.columns else "agent"
        mask = ~out[agent_col].astype(str).isin(drop_agents)
        out = out[mask].copy()
        meta["drop_agents"] = list(drop_agents)
        meta["events_after_agent_filter"] = int(len(out))
    return out.reset_index(drop=True), meta


def subsample_case_split(
    fit: pd.DataFrame,
    hold: pd.DataFrame,
    fit_max: int | None = None,
    hold_max: int | None = None,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Случайный subsample кейсов в fit/hold (для тяжёлых логов)."""
    rng = np.random.default_rng(seed)
    meta: dict = {"seed": seed}
    fit_cases = fit["case:concept:name"].unique()
    hold_cases = hold["case:concept:name"].unique()
    if fit_max is not None and len(fit_cases) > fit_max:
        pick = rng.choice(fit_cases, size=fit_max, replace=False)
        fit = fit[fit["case:concept:name"].isin(pick)].copy()
        meta["fit_cases_sampled"] = int(fit_max)
    if hold_max is not None and len(hold_cases) > hold_max:
        pick = rng.choice(hold_cases, size=hold_max, replace=False)
        hold = hold[hold["case:concept:name"].isin(pick)].copy()
        meta["hold_cases_sampled"] = int(hold_max)
    meta["fit_cases"] = int(fit["case:concept:name"].nunique())
    meta["hold_cases"] = int(hold["case:concept:name"].nunique())
    meta["fit_events"] = int(len(fit))
    meta["hold_events"] = int(len(hold))
    return fit, hold, meta


def infer_roles_from_frame(df: pd.DataFrame, role_mode: str = "activity_prefix") -> dict[str, str]:
    """
    role_mode:
      activity_prefix — A_/O_/W_ (BPIC2012)
      procurement — семейство активности (BPIC2019)
      agent — роль = агент (отделение как мембрана)
      specialism — колонка Specialism code / case:Specialism code
    """
    from collections import Counter, defaultdict

    agent_s = df["agent"].astype(str) if "agent" in df.columns else df["org:resource"].astype(str)
    if role_mode == "agent":
        return {a: a for a in agent_s.unique()}
    if role_mode == "procurement":
        votes = defaultdict(Counter)
        acts = df["concept:name"].astype(str)
        for agent, act in zip(agent_s, acts):
            votes[agent][infer_role_procurement(act)] += 1
        return {a: c.most_common(1)[0][0] for a, c in votes.items()}
    if role_mode == "specialism":
        spec_col = None
        for c in ("Specialism code", "case:Specialism code"):
            if c in df.columns:
                spec_col = c
                break
        if spec_col is None:
            return {a: a for a in agent_s.unique()}
        votes: dict[str, Counter] = defaultdict(Counter)
        for agent, spec in zip(agent_s, df[spec_col].astype(str)):
            votes[agent][spec] += 1
        return {a: c.most_common(1)[0][0] for a, c in votes.items()}
    votes = defaultdict(Counter)
    acts = df["concept:name"].astype(str)
    for agent, act in zip(agent_s, acts):
        votes[agent][infer_role(act)] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}
