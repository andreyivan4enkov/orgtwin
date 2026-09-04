"""Фоновые задачи сборки OrgModel с прогрессом."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def create_job(donor_id: str, *, force: bool, with_queue: bool) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "donor_id": donor_id,
            "force": force,
            "with_queue": with_queue,
            "status": "queued",
            "pct": 0,
            "stage": "В очереди",
            "detail": "",
            "error": None,
            "started_at": _now(),
            "updated_at": _now(),
            "finished_at": None,
        }
    return job_id


def update_job(job_id: str, *, pct: int, stage: str, detail: str = "", status: str = "running") -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["pct"] = int(max(0, min(100, pct)))
        job["stage"] = stage
        job["detail"] = detail
        job["status"] = status
        job["updated_at"] = _now()


def finish_job(job_id: str, *, ok: bool, error: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "done" if ok else "error"
        job["pct"] = 100 if ok else job.get("pct", 0)
        job["error"] = error
        job["finished_at"] = _now()
        job["updated_at"] = _now()
        if ok:
            job["stage"] = "Готово"
            job["detail"] = ""


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def progress_cb(job_id: str) -> Callable[[int, str, str], None]:
    def _cb(pct: int, stage: str, detail: str = "") -> None:
        update_job(job_id, pct=pct, stage=stage, detail=detail)

    return _cb


def start_build_thread(job_id: str, runner: Callable[[], None]) -> None:
    def _run() -> None:
        try:
            update_job(job_id, pct=1, stage="Старт", detail="")
            runner()
            finish_job(job_id, ok=True)
        except Exception as e:
            finish_job(job_id, ok=False, error=str(e))

    threading.Thread(target=_run, daemon=True, name=f"build-{job_id}").start()
