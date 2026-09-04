"""
FastAPI: OrgTwin web backend (полное ТЗ S1–S9).

  .venv/bin/uvicorn apps.api.main:app --reload --app-dir .
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin.api import donor_registry  # noqa: E402
from orgtwin.api.donor_registry import MAX_UPLOAD_BYTES, UPLOAD_ROOT  # noqa: E402
from orgtwin.api.greenfield import TEMPLATES, synthesize_event_log  # noqa: E402
from orgtwin.api.membrane_ops import (  # noqa: E402
    membrane_bit_budget,
    prune_and_score,
    prune_weak_edges,
    suggest_collapse_paths,
    topology_diff,
)
from orgtwin.api.ops_layer import (  # noqa: E402
    ShiftCalendar,
    default_office_shifts,
    run_cascade_scenario,
)
from orgtwin.api.optimize import greedy_optimize  # noqa: E402
from orgtwin.api.org_model import (  # noqa: E402
    OrgModelStore,
    list_donors,
    resolve_donor_spec,
)
from orgtwin.api.build_jobs import create_job, get_job, progress_cb, start_build_thread  # noqa: E402
from orgtwin.api.snapshots import delete_snapshot, list_snapshots, load_snapshot, save_snapshot  # noqa: E402
from orgtwin.api.reporting import (  # noqa: E402
    arena_passed,
    compare_scenarios,
    list_scenarios,
    load_scenario,
    render_director_html,
    save_arena_attempt,
    save_scenario,
)
from orgtwin.ingest.adapters import Bitrix24Adapter, OneCAdapter, SapAdapter  # noqa: E402

store = OrgModelStore()
app = FastAPI(title="OrgTwin API", version="0.12.0")

_API_KEY = os.environ.get("ORGTWIN_API_KEY", "").strip()
_CORS = os.environ.get("ORGTWIN_CORS", "*").strip()
_origins = ["*"] if _CORS == "*" else [o.strip() for o in _CORS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not _API_KEY:
        return
    if (x_api_key or "") != _API_KEY:
        raise HTTPException(401, "Нужен заголовок X-API-Key")


class DesignPayload(BaseModel):
    roles: list[dict] = Field(default_factory=list)
    agents: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    capacities: dict[str, int] = Field(default_factory=dict)


class WhatIfPayload(BaseModel):
    exclude_agents: list[str] = Field(default_factory=list)
    exclude_roles: list[str] = Field(default_factory=list)
    role_multipliers: dict[str, float] = Field(default_factory=dict)
    global_multiplier: float = 1.0


class PrunePayload(BaseModel):
    min_support: int = 30
    lambda_entropy: float = 0.05
    apply: bool = False
    edge_min_weight: float | None = None


class CascadePayload(BaseModel):
    exclude_agents: list[str] = Field(default_factory=list)
    recovery: str = "role_peers"
    sla_hours: float | None = None


class OptimizePayload(BaseModel):
    weights: dict[str, float] = Field(default_factory=lambda: {"queue": 1.0, "sla": 50.0, "H": 0.1})
    max_iters: int = 12
    wall_sec: float = 45.0
    apply_best: bool = False


class GreenfieldPayload(BaseModel):
    id: str = "GF_CUSTOM"
    label: str = "Greenfield"
    template: str | None = "credit"
    design: DesignPayload | None = None
    n_cases: int = 200


class ScenarioPayload(BaseModel):
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ArenaPayload(BaseModel):
    donor_id: str = "BPIC2012"
    exclude_agents: list[str] = Field(default_factory=list)
    peak_after: float
    elapsed_sec: float = 0.0
    threshold: float = 5.0


class ShiftsPayload(BaseModel):
    windows: dict[str, list[dict]] = Field(default_factory=dict)
    use_default_office: bool = False


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "orgtwin", "version": "0.12.0", "auth": bool(_API_KEY)}


@app.get("/api/donors")
def donors(_: None = Depends(require_api_key)) -> list[dict]:
    return list_donors()


@app.post("/api/donors/upload")
async def upload_donor(
    file: UploadFile = File(...),
    donor_id: str = Form(""),
    label: str = Form(""),
    agent_column: str = Form("org:resource"),
    role_mode: str = Form("activity_prefix"),
    case_col: str = Form("case_id"),
    activity_col: str = Form("activity"),
    time_col: str = Form("timestamp"),
    agent_col_csv: str = Form("agent"),
    _: None = Depends(require_api_key),
) -> dict:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Файл больше лимита {MAX_UPLOAD_BYTES} байт")
    name = file.filename or "log.xes"
    ext = Path(name).suffix.lower()
    if ext not in (".xes", ".gz", ".csv"):
        # .xes.gz
        if name.lower().endswith(".xes.gz"):
            ext = ".xes.gz"
        else:
            raise HTTPException(400, "Нужен .xes / .xes.gz / .csv")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", (donor_id or Path(name).stem))[:40] or "upload"
    from orgtwin.api.org_model import DONORS

    if slug in DONORS:
        slug = f"U_{slug}"
    folder = UPLOAD_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    if ext == ".csv":
        fname = "events.csv"
        fmt = "csv"
    elif ext == ".xes.gz" or name.lower().endswith(".xes.gz"):
        fname = "events.xes.gz"
        fmt = "xes"
    else:
        fname = "events.xes"
        fmt = "xes"
    path = folder / fname
    path.write_bytes(raw)
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    mapping = None
    if fmt == "csv":
        mapping = {
            case_col: "case:concept:name",
            activity_col: "concept:name",
            time_col: "time:timestamp",
            agent_col_csv: "org:resource",
        }
    spec = donor_registry.save_custom_donor(
        {
            "id": slug,
            "label": label or f"Загрузка {name}",
            "xes_path": rel,
            "agent_column": agent_column,
            "role_mode": role_mode,
            "origin": "upload",
            "format": fmt,
            "mapping": mapping,
            "subsample_fit": 3000,
            "subsample_hold": 1500,
        }
    )
    store._models.pop(slug, None)
    store._runtime.pop(slug, None)
    try:
        model = store.build(slug, force=True, with_queue=False)
    except Exception as e:
        raise HTTPException(500, f"Лог сохранён, но сборка OrgModel не удалась: {e}") from e
    return {"donor": spec, "ingest": model.get("ingest"), "metrics": model.get("metrics")}


@app.delete("/api/donors/{donor_id}")
def delete_donor(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    from orgtwin.api.org_model import DONORS

    if donor_id in DONORS:
        raise HTTPException(400, "Демо-сеты на открытых данных удалять нельзя")
    ok = donor_registry.delete_custom_donor(donor_id)
    store._models.pop(donor_id, None)
    store._runtime.pop(donor_id, None)
    cache = store.cache_path(donor_id)
    cache.unlink(missing_ok=True)
    if not ok:
        raise HTTPException(404, "Донор не найден")
    return {"deleted": donor_id}


@app.post("/api/donors/greenfield")
def create_greenfield(body: GreenfieldPayload, _: None = Depends(require_api_key)) -> dict:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", body.id)[:40] or "GF_CUSTOM"
    if body.template and body.template in TEMPLATES:
        tpl = TEMPLATES[body.template]
        design = {
            "roles": tpl["roles"],
            "agents": tpl["agents"],
            "edges": tpl["edges"],
            "capacities": {a["id"]: int(a.get("capacity", 1)) for a in tpl["agents"]},
        }
        label = body.label or tpl["label"]
    else:
        d = body.design.model_dump() if body.design else {"roles": [], "agents": [], "edges": [], "capacities": {}}
        design = d
        label = body.label
    df = synthesize_event_log(design, n_cases=body.n_cases)
    folder = UPLOAD_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / "events.csv"
    df.to_csv(csv_path, index=False)
    rel = str(csv_path.relative_to(ROOT)).replace("\\", "/")
    spec = donor_registry.save_custom_donor(
        {
            "id": slug,
            "label": label,
            "xes_path": rel,
            "agent_column": "org:resource",
            "role_mode": "activity_prefix",
            "origin": "greenfield",
            "format": "csv",
            "assumption": True,
            "fit_months": 7,
            "holdout_months": 3,
            "subsample_fit": None,
            "subsample_hold": None,
            "mapping": {
                "case:concept:name": "case:concept:name",
                "concept:name": "concept:name",
                "time:timestamp": "time:timestamp",
                "org:resource": "org:resource",
            },
        }
    )
    # fix mapping for already-normalized columns — CsvEventsAdapter handles native names
    store.put_design(slug, design)
    store._models.pop(slug, None)
    store._runtime.pop(slug, None)
    model = store.build(slug, force=True, with_queue=True)
    return {"donor": spec, "model_metrics": model.get("metrics"), "assumption": True, "templates": list(TEMPLATES)}


@app.get("/api/templates")
def templates(_: None = Depends(require_api_key)) -> dict:
    return {k: {"label": v["label"], "n_agents": len(v["agents"])} for k, v in TEMPLATES.items()}


@app.get("/api/org-model/{donor_id}")
def org_model(
    donor_id: str, force: bool = False, with_queue: bool = True, _: None = Depends(require_api_key)
) -> dict:
    try:
        return store.build(donor_id, force=force, with_queue=with_queue)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Ошибка сборки OrgModel: {e}") from e


class BuildStartPayload(BaseModel):
    force: bool = False
    with_queue: bool = True


@app.post("/api/org-model/{donor_id}/build")
def start_org_build(donor_id: str, body: BuildStartPayload | None = None, _: None = Depends(require_api_key)) -> dict:
    body = body or BuildStartPayload()
    job_id = create_job(donor_id, force=body.force, with_queue=body.with_queue)
    cb = progress_cb(job_id)

    def runner() -> None:
        store.build(
            donor_id,
            force=body.force,
            with_queue=body.with_queue,
            on_progress=cb,
        )

    start_build_thread(job_id, runner)
    return {"job_id": job_id, "donor_id": donor_id}


@app.get("/api/build/{job_id}")
def build_status(job_id: str, _: None = Depends(require_api_key)) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    out = dict(job)
    if job["status"] == "done":
        try:
            out["model"] = store.build(job["donor_id"], force=False, with_queue=job.get("with_queue", True))
        except Exception as e:
            out["status"] = "error"
            out["error"] = str(e)
    return out


class SnapshotSavePayload(BaseModel):
    name: str
    note: str = ""
    with_queue: bool = True


@app.get("/api/snapshots/{donor_id}")
def snapshots_list(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    return {"donor_id": donor_id, "items": list_snapshots(donor_id)}


@app.post("/api/snapshots/{donor_id}")
def snapshots_save(donor_id: str, body: SnapshotSavePayload, _: None = Depends(require_api_key)) -> dict:
    model = store.build(donor_id, force=False, with_queue=body.with_queue)
    return save_snapshot(donor_id, body.name, model, note=body.note)


class SnapshotLoadPayload(BaseModel):
    name: str


@app.post("/api/snapshots/{donor_id}/load")
def snapshots_load(donor_id: str, body: SnapshotLoadPayload, _: None = Depends(require_api_key)) -> dict:
    snap = load_snapshot(donor_id, body.name)
    if not snap:
        raise HTTPException(404, "Снимок не найден")
    model = snap.get("model") or {}
    # положить в кэш store
    store._models[donor_id] = model
    cache = store.cache_path(donor_id)
    cache.write_text(
        __import__("json").dumps(model, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return {"loaded": body.name, "model": model}


@app.delete("/api/snapshots/{donor_id}/{name}")
def snapshots_delete(donor_id: str, name: str, _: None = Depends(require_api_key)) -> dict:
    if not delete_snapshot(donor_id, name):
        raise HTTPException(404, "Снимок не найден")
    return {"deleted": name}


@app.get("/api/agent/{donor_id}/{agent_id}")
def agent_detail(donor_id: str, agent_id: str, _: None = Depends(require_api_key)) -> dict:
    model = store.build(donor_id, with_queue=False)
    agent = next((a for a in model["agents"] if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(404, f"Агент {agent_id} не найден")
    rules = [r for r in model["rules"] if r["agent_id"] == agent_id]
    edges_out = [e for e in model["edges"] if e["from_agent"] == agent_id][:20]
    edges_in = [e for e in model["edges"] if e["to_agent"] == agent_id][:20]
    return {"agent": agent, "rules": rules, "edges_out": edges_out, "edges_in": edges_in}


@app.post("/api/queue-stress/{donor_id}")
def queue_stress(donor_id: str, force: bool = True, _: None = Depends(require_api_key)) -> dict:
    try:
        model = store.build(donor_id, force=force, with_queue=True)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {
        "donor_id": donor_id,
        "queue_slices": model.get("queue_slices"),
        "honesty": model.get("honesty"),
    }


@app.post("/api/whatif/{donor_id}")
def whatif(donor_id: str, body: WhatIfPayload, _: None = Depends(require_api_key)) -> dict:
    try:
        return store.run_whatif(
            donor_id,
            exclude_agents=body.exclude_agents,
            exclude_roles=body.exclude_roles,
            role_multipliers=body.role_multipliers,
            global_multiplier=body.global_multiplier,
        )
    except Exception as e:
        raise HTTPException(500, f"Сценарий не посчитан: {e}") from e


@app.get("/api/design/{donor_id}")
def get_design(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    return store.get_design(donor_id)


@app.put("/api/design/{donor_id}")
def put_design(donor_id: str, body: DesignPayload, _: None = Depends(require_api_key)) -> dict:
    return store.put_design(donor_id, body.model_dump())


@app.post("/api/membrane/{donor_id}/prune")
def membrane_prune(donor_id: str, body: PrunePayload, _: None = Depends(require_api_key)) -> dict:
    rt = store.ensure_runtime(donor_id)
    pol = rt["pol"]
    # fit из полного rebuild — берём hold как proxy если fit нет; лучше rebuild
    model = store.build(donor_id, with_queue=False)
    spec = resolve_donor_spec(donor_id)
    # пересоберём fit через force path internals: use hold for score, fit from runtime if stored
    hold = rt["hold"]
    # для prune нужен fit — загрузим кратко
    from orgtwin.api.org_model import _resolve_xes
    from orgtwin.ingest.adapters import CsvEventsAdapter, normalize_event_table
    from orgtwin.ingest.xes_loader import fit_holdout_split, filter_event_table, load_event_table

    path = _resolve_xes(spec)
    if spec.format == "csv" or path.suffix.lower() == ".csv":
        df = normalize_event_table(CsvEventsAdapter(path, mapping=spec.mapping).load(), spec.agent_column)
    else:
        df = load_event_table(path, agent_col=spec.agent_column or None)
    if spec.time_filter_from:
        df, _ = filter_event_table(df, time_from=spec.time_filter_from)
    fit, hold2, _ = fit_holdout_split(df, fit_months=spec.fit_months, holdout_months=spec.holdout_months)
    result = prune_and_score(
        pol,
        fit,
        hold2,
        min_support=body.min_support,
        lambda_entropy=body.lambda_entropy,
        agent_col=spec.agent_column or None,
        context_col=spec.context_column or None,
    )
    bundle2 = result.pop("bundle")
    edge_info = None
    edges = model.get("edges") or []
    if body.edge_min_weight is not None:
        edge_info = prune_weak_edges(edges, min_weight=float(body.edge_min_weight))
        edges_after = edge_info["edges"]
    else:
        edges_after = edges
    collapse = suggest_collapse_paths(edges_after)
    diff = topology_diff(edges, edges_after)
    if body.apply:
        rt["pol"] = bundle2
        store._runtime[donor_id] = rt
        # помечаем модель
        model["membrane_pruned"] = result.get("pruned")
        model["edges"] = edges_after
        store._models[donor_id] = model
    bits = membrane_bit_budget(bundle2, fit)
    return {
        "donor_id": donor_id,
        "applied": body.apply,
        **{k: v for k, v in result.items()},
        "bits": bits,
        "edges": edge_info,
        "collapse_suggestions": collapse,
        "topology_diff": diff,
    }


@app.get("/api/membrane/{donor_id}/budget")
def membrane_budget(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    rt = store.ensure_runtime(donor_id)
    # approximate with hold framed via agents entropy from model
    model = store.build(donor_id, with_queue=False)
    rows = [
        {
            "agent_id": a["id"],
            "role_id": a["role_id"],
            "H_bits": a.get("mean_H_bits"),
            "n_events": a.get("n_events"),
        }
        for a in model.get("agents", [])
    ]
    hs = [r["H_bits"] for r in rows if r["H_bits"] is not None]
    return {
        "donor_id": donor_id,
        "agents": rows[:80],
        "mean_H_bits": float(sum(hs) / len(hs)) if hs else None,
        "note": "Биты на типичном входе агента (local_minima)",
    }


@app.post("/api/cascade/{donor_id}")
def cascade(donor_id: str, body: CascadePayload, _: None = Depends(require_api_key)) -> dict:
    rt = store.ensure_runtime(donor_id)
    spec = rt["spec"]
    try:
        return run_cascade_scenario(
            rt["hold"],
            rt["pol"],
            exclude_agents=body.exclude_agents,
            terminal_prefixes=spec.terminal_prefixes,
            recovery=body.recovery,
            sla_hours=float(body.sla_hours if body.sla_hours is not None else getattr(spec, "sla_hours", 72)),
        )
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.put("/api/shifts/{donor_id}")
def put_shifts(donor_id: str, body: ShiftsPayload, _: None = Depends(require_api_key)) -> dict:
    model = store.build(donor_id, with_queue=False)
    if body.use_default_office:
        cal = default_office_shifts([a["id"] for a in model.get("agents", [])])
    else:
        cal = ShiftCalendar.from_dict(body.windows)
    path = store.cache_dir / f"shifts_{donor_id}.json"
    path.write_text(__import__("json").dumps(cal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "donor_id": donor_id,
        "n_agents_with_windows": len(cal.windows),
        "assumption": not body.windows and body.use_default_office,
        "note": "Смены сохранены; DES учитывает недоступность в расширенных сценариях каскада/отчёта",
    }


@app.get("/api/shifts/{donor_id}")
def get_shifts(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    path = store.cache_dir / f"shifts_{donor_id}.json"
    if not path.exists():
        return {"donor_id": donor_id, "windows": {}, "assumption": True}
    import json

    return {"donor_id": donor_id, "windows": json.loads(path.read_text(encoding="utf-8")), "assumption": False}


@app.post("/api/optimize/{donor_id}")
def optimize(donor_id: str, body: OptimizePayload, _: None = Depends(require_api_key)) -> dict:
    rt = store.ensure_runtime(donor_id)
    model = store.build(donor_id, with_queue=False)
    hs = [a.get("mean_H_bits") for a in model.get("agents", []) if a.get("mean_H_bits") is not None]
    mean_h = float(sum(hs) / len(hs)) if hs else None
    out = greedy_optimize(
        rt["hold"],
        rt["pol"],
        agents=model.get("agents") or [],
        terminal_prefixes=rt["spec"].terminal_prefixes,
        weights=body.weights,
        max_iters=body.max_iters,
        wall_sec=body.wall_sec,
        sla_hours=float(getattr(rt["spec"], "sla_hours", 72)),
        mean_H_bits=mean_h,
    )
    if body.apply_best:
        best = out["best"]
        design = store.get_design(donor_id)
        caps = dict(design.get("capacities") or {})
        caps.update(best.get("capacities") or {})
        design["capacities"] = caps
        store.put_design(donor_id, design)
        out["applied"] = True
        out["design_patch"] = {"capacities": best.get("capacities"), "exclude_agents": best.get("exclude_agents")}
    else:
        out["applied"] = False
    return out


@app.get("/api/report/{donor_id}")
def report_html(donor_id: str, _: None = Depends(require_api_key)) -> HTMLResponse:
    model = store.build(donor_id, with_queue=True)
    html = render_director_html(model)
    return HTMLResponse(html)


@app.get("/api/report/{donor_id}.pdf")
def report_pdf(donor_id: str, _: None = Depends(require_api_key)) -> Response:
    """PDF через print-HTML (клиент может Save as PDF); отдаём HTML с MIME для печати."""
    model = store.build(donor_id, with_queue=True)
    html = render_director_html(model)
    # без weasyprint в deps — отдаём HTML; заголовок подсказывает печать
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="orgtwin_{donor_id}.html"'},
    )


@app.post("/api/scenarios/{donor_id}")
def post_scenario(donor_id: str, body: ScenarioPayload, _: None = Depends(require_api_key)) -> dict:
    return save_scenario(donor_id, body.name, body.payload)


@app.get("/api/scenarios/{donor_id}")
def get_scenarios(donor_id: str, _: None = Depends(require_api_key)) -> dict:
    return {"donor_id": donor_id, "names": list_scenarios(donor_id)}


@app.get("/api/scenarios/{donor_id}/compare")
def scenarios_compare(donor_id: str, a: str = "baseline", b: str = "after", _: None = Depends(require_api_key)) -> dict:
    sa, sb = load_scenario(donor_id, a), load_scenario(donor_id, b)
    if not sa or not sb:
        raise HTTPException(404, "Нужны оба сценария")
    return compare_scenarios(sa, sb)


@app.post("/api/arena/attempt")
def arena_attempt(body: ArenaPayload, _: None = Depends(require_api_key)) -> dict:
    passed = arena_passed(body.peak_after, body.threshold)
    row = save_arena_attempt(
        {
            **body.model_dump(),
            "passed": passed,
            "ts": time.time(),
        }
    )
    return {**row, "verdict": "допущен к пилоту" if passed else "ещё тренировка"}


@app.get("/api/connectors/dry-run")
def connectors_dry_run(_: None = Depends(require_api_key)) -> dict:
    return {
        "bitrix24": Bitrix24Adapter({}).dry_run(),
        "onec": OneCAdapter({}).dry_run(),
        "sap": SapAdapter({}).dry_run(),
    }


@app.get("/api/protocol/checklist")
def protocol_checklist(_: None = Depends(require_api_key)) -> dict:
    return {
        "min_dataset": [
            "орг: ≤15 FTE с ролями",
            "поток событий ≥12 месяцев",
            "case id + activity + timestamp + agent",
            "без критичных PII или с маскированием",
        ],
        "split_target": {"fit_months": 7, "holdout_months": 3},
        "acceptance_v1": [
            "next-step holdout не случаен",
            "очередь ×2 растёт предсказуемо",
            "what-if / optimize даёт воспроизводимый diff",
            "отчёт директору HTML",
            "upload своего CSV/XES",
        ],
    }


# optional static SPA
_web_dist = ROOT / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
