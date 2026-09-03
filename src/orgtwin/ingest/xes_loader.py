"""Загрузка одного XES-донора → плоский event table."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.conversion.log import converter as log_converter


REQUIRED_COLS = ("case:concept:name", "concept:name", "time:timestamp")


def load_event_table(xes_path: str | Path) -> pd.DataFrame:
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
    if "org:resource" not in df.columns:
        df["org:resource"] = "UNKNOWN"
    df["org:resource"] = df["org:resource"].fillna("UNKNOWN").astype(str)
    if "lifecycle:transition" not in df.columns:
        df["lifecycle:transition"] = None
    # стабильный порядок
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
    BPIC 2012 покрывает ~5.5 месяца — делим пропорционально идее 7→3:
    fit ≈ первые fit_months, holdout ≈ следующие holdout_months от старта.
    Кейс попадает в окно по timestamp первого события.
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
