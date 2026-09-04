"""Сохранённые снимки собранных OrgModel."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_ROOT = ROOT / "data" / "derived" / "snapshots"


def _safe_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ _.-]+", "_", name.strip())[:64]
    return s.strip(" ._") or "snapshot"


def _dir(donor_id: str) -> Path:
    d = SNAPSHOT_ROOT / donor_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_snapshots(donor_id: str) -> list[dict[str, Any]]:
    out = []
    folder = _dir(donor_id)
    for p in sorted(folder.glob("*.json"), key=lambda x: -x.stat().st_mtime):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "name": meta.get("name") or p.stem,
                "saved_at": meta.get("saved_at"),
                "build_wall_sec": (meta.get("model") or {}).get("build_wall_sec"),
                "n_agents": len((meta.get("model") or {}).get("agents") or []),
                "has_queue": bool((meta.get("model") or {}).get("queue_slices")),
                "note": meta.get("note") or "",
            }
        )
    return out


def save_snapshot(donor_id: str, name: str, model: dict, *, note: str = "") -> dict:
    safe = _safe_name(name)
    path = _dir(donor_id) / f"{safe}.json"
    payload = {
        "name": safe,
        "donor_id": donor_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": note,
        "model": model,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"name": safe, "saved_at": payload["saved_at"], "path": str(path.relative_to(ROOT))}


def load_snapshot(donor_id: str, name: str) -> dict | None:
    path = _dir(donor_id) / f"{_safe_name(name)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_snapshot(donor_id: str, name: str) -> bool:
    path = _dir(donor_id) / f"{_safe_name(name)}.json"
    if not path.exists():
        return False
    path.unlink()
    return True
