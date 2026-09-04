"""
Реестр пользовательских доноров (upload / greenfield) и отчёт ingest.

Файлы: data/uploads/{donor_id}/…, индекс — data/uploads/registry.json.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = ROOT / "data" / "uploads"
REGISTRY_PATH = UPLOAD_ROOT / "registry.json"
MAX_UPLOAD_BYTES = 80_000_000

_REQUIRED_SPEC_KEYS = ("id", "label", "xes_path")


def ensure_upload_root() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def _default_registry() -> dict[str, Any]:
    return {"version": 1, "donors": {}}


def _read_registry_raw() -> dict[str, Any]:
    ensure_upload_root()
    if not REGISTRY_PATH.exists():
        return _default_registry()
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return _default_registry()
    donors = raw.get("donors")
    if not isinstance(donors, dict):
        raw["donors"] = {}
    raw.setdefault("version", 1)
    return raw


def _write_registry_raw(raw: dict[str, Any]) -> None:
    ensure_upload_root()
    REGISTRY_PATH.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_donor_spec(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Привести dict к DonorSpec-like форме для registry."""
    origin = str(spec_dict.get("origin") or "upload").lower()
    if origin not in ("upload", "greenfield"):
        raise ValueError(f"origin должен быть upload|greenfield, получено: {origin}")

    # greenfield может быть без файла (пустой xes_path)
    if origin == "greenfield":
        missing = [k for k in ("id", "label") if not spec_dict.get(k)]
    else:
        missing = [k for k in _REQUIRED_SPEC_KEYS if not spec_dict.get(k)]
    if missing:
        raise ValueError(f"В spec нет обязательных полей: {', '.join(missing)}")

    donor_id = str(spec_dict["id"]).strip()
    if not donor_id or "/" in donor_id or "\\" in donor_id or ".." in donor_id:
        raise ValueError(f"Некорректный id донора: {donor_id!r}")

    fmt = str(spec_dict.get("format") or "xes").lower()
    if fmt not in ("xes", "csv"):
        raise ValueError(f"format должен быть xes|csv, получено: {fmt}")

    xes_path = str(spec_dict.get("xes_path") or "").replace("\\", "/").lstrip("/")
    out: dict[str, Any] = {
        "id": donor_id,
        "label": str(spec_dict["label"]).strip() or donor_id,
        "xes_path": xes_path,
        "agent_column": str(spec_dict.get("agent_column") or "org:resource"),
        "context_column": str(spec_dict.get("context_column") or ""),
        "role_mode": str(spec_dict.get("role_mode") or "activity_prefix"),
        "fit_months": int(spec_dict.get("fit_months") or 3),
        "holdout_months": int(spec_dict.get("holdout_months") or 2),
        "origin": origin,
        "format": fmt,
    }
    mapping = spec_dict.get("mapping")
    if mapping is not None:
        if not isinstance(mapping, dict):
            raise ValueError("mapping должен быть dict[str, str]")
        out["mapping"] = {str(k): str(v) for k, v in mapping.items()}

    # опциональные поля DonorSpec (если передали)
    for key in (
        "time_filter_from",
        "subsample_fit",
        "subsample_hold",
        "max_iter",
        "queue_hold_max",
    ):
        if key in spec_dict and spec_dict[key] is not None:
            out[key] = spec_dict[key]
    if "terminal_prefixes" in spec_dict and spec_dict["terminal_prefixes"] is not None:
        out["terminal_prefixes"] = list(spec_dict["terminal_prefixes"])

    return out


def load_custom_donors() -> dict[str, dict[str, Any]]:
    """id → DonorSpec-like dict из registry.json."""
    raw = _read_registry_raw()
    donors: dict[str, dict[str, Any]] = {}
    for key, spec in (raw.get("donors") or {}).items():
        if not isinstance(spec, dict):
            continue
        try:
            donors[str(key)] = normalize_donor_spec({**spec, "id": spec.get("id", key)})
        except ValueError:
            continue
    return donors


def save_custom_donor(spec_dict: dict[str, Any]) -> dict[str, Any]:
    """Создать/обновить запись в реестре. Возвращает нормализованный spec."""
    spec = normalize_donor_spec(spec_dict)
    raw = _read_registry_raw()
    raw.setdefault("donors", {})[spec["id"]] = spec
    _write_registry_raw(raw)
    donor_dir = UPLOAD_ROOT / spec["id"]
    donor_dir.mkdir(parents=True, exist_ok=True)
    return spec


def delete_custom_donor(donor_id: str) -> bool:
    """
    Удалить донора из реестра и каталог data/uploads/{id}/.
    True если запись была; False если не найдена.
    """
    donor_id = str(donor_id).strip()
    raw = _read_registry_raw()
    donors = raw.setdefault("donors", {})
    existed = donor_id in donors
    if existed:
        del donors[donor_id]
        _write_registry_raw(raw)
    donor_dir = UPLOAD_ROOT / donor_id
    if donor_dir.exists() and donor_dir.is_dir():
        shutil.rmtree(donor_dir)
        existed = True
    return existed


def resolve_upload_path(xes_path: str) -> Path:
    """Относительный xes_path → абсолютный Path под ROOT."""
    p = Path(xes_path)
    if p.is_absolute():
        return p
    return ROOT / p


def ingest_report(df: pd.DataFrame, agent_col: str) -> dict[str, Any]:
    """
    Краткий отчёт качества загруженного лога.

    Возвращает: n_events, n_cases, n_agents, unknown_frac,
    timestamp_gaps, span_days.
    """
    n_events = int(len(df))
    if n_events == 0:
        return {
            "n_events": 0,
            "n_cases": 0,
            "n_agents": 0,
            "unknown_frac": 0.0,
            "timestamp_gaps": {
                "n_gaps_gt_1d": 0,
                "max_gap_days": 0.0,
                "median_dt_sec": None,
            },
            "span_days": 0.0,
        }

    case_col = "case:concept:name"
    n_cases = int(df[case_col].nunique()) if case_col in df.columns else 0

    col = agent_col or "org:resource"
    if col in df.columns:
        agents = df[col].fillna("UNKNOWN").astype(str).str.strip()
    elif "org:resource" in df.columns:
        agents = df["org:resource"].fillna("UNKNOWN").astype(str).str.strip()
    else:
        agents = pd.Series(["UNKNOWN"] * n_events, index=df.index)

    n_agents = int(agents.nunique())
    unknown = agents.str.upper().isin({"", "UNKNOWN", "NONE", "NAN", "NAT"})
    unknown_frac = float(unknown.mean())

    if "time:timestamp" not in df.columns:
        return {
            "n_events": n_events,
            "n_cases": n_cases,
            "n_agents": n_agents,
            "unknown_frac": unknown_frac,
            "timestamp_gaps": {
                "n_gaps_gt_1d": 0,
                "max_gap_days": 0.0,
                "median_dt_sec": None,
            },
            "span_days": 0.0,
        }

    ts = pd.to_datetime(df["time:timestamp"], utc=True, errors="coerce").dropna()
    if ts.empty:
        span_days = 0.0
        gaps = {"n_gaps_gt_1d": 0, "max_gap_days": 0.0, "median_dt_sec": None}
    else:
        t_min, t_max = ts.min(), ts.max()
        span_days = float((t_max - t_min).total_seconds() / 86400.0)
        sorted_ts = ts.sort_values()
        deltas = sorted_ts.diff().dt.total_seconds().dropna()
        large = deltas[deltas > 86400.0]
        gaps = {
            "n_gaps_gt_1d": int(len(large)),
            "max_gap_days": float(large.max() / 86400.0) if len(large) else 0.0,
            "median_dt_sec": float(deltas.median()) if len(deltas) else None,
        }

    return {
        "n_events": n_events,
        "n_cases": n_cases,
        "n_agents": n_agents,
        "unknown_frac": unknown_frac,
        "timestamp_gaps": gaps,
        "span_days": span_days,
    }
