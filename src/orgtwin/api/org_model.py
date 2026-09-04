"""
Сборка OrgModel для веб-UI из лога (диагност + рёбра handover + срезы очереди).
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from orgtwin.api import donor_registry
from orgtwin.api.donor_registry import MAX_UPLOAD_BYTES, UPLOAD_ROOT, ingest_report
from orgtwin.api.ops_layer import duration_percentiles, sla_metrics
from orgtwin.config.constants import ExperimentConfig, PolicyConfig, SimConfig, TimingConfig
from orgtwin.diag.local_minima import diagnose_local_minima
from orgtwin.ingest.adapters import CsvEventsAdapter, XesAdapter
from orgtwin.ingest.xes_loader import filter_event_table, fit_holdout_split, subsample_case_split
from orgtwin.policy.counts import next_step_accuracy_counts, train_count_policies
from orgtwin.policy.softmax import next_step_accuracy, train_softmax_policies
from orgtwin.sim.queue_des import is_ghost_agent, simulate_queue

ROOT = Path(__file__).resolve().parents[3]
# bump при смене схемы метрик/признаков — старый ui_cache не подхватываем
ORG_MODEL_CACHE_VER = 2


@dataclass
class DonorSpec:
    id: str
    label: str
    xes_path: str
    agent_column: str = "org:resource"
    context_column: str = ""
    role_mode: str = "activity_prefix"
    fit_months: int = 3
    holdout_months: int = 2
    time_filter_from: str | None = None
    subsample_fit: int | None = 4000
    subsample_hold: int | None = 2000
    max_iter: int = 250
    queue_hold_max: int = 800
    sla_hours: float = 72.0
    origin: str = "builtin"  # builtin | upload | greenfield
    format: str = "xes"  # xes | csv
    mapping: dict[str, str] | None = None
    assumption: bool = False
    terminal_prefixes: tuple[str, ...] = (
        "A_CANCELLED",
        "A_DECLINED",
        "A_APPROVED",
        "A_REGISTERED",
    )


DONORS: dict[str, DonorSpec] = {
    "BPIC2012": DonorSpec(
        id="BPIC2012",
        label="Кредиты NL (BPIC 2012)",
        xes_path="data/raw/BPI_Challenge_2012.xes",
        role_mode="activity_prefix",
    ),
    "BPIC2019": DonorSpec(
        id="BPIC2019",
        label="Закупки NL (BPIC 2019)",
        xes_path="data/raw/BPI_Challenge_2019.xes",
        context_column="Cumulative net worth (EUR)",
        role_mode="procurement",
        time_filter_from="2018-01-01",
        subsample_fit=3000,
        subsample_hold=1500,
        queue_hold_max=500,
        terminal_prefixes=(
            "Clear Invoice",
            "Delete Purchase Order Item",
            "Cancel Invoice Receipt",
        ),
    ),
    "HOSPITAL2011": DonorSpec(
        id="HOSPITAL2011",
        label="Госпиталь (Hospital Log 2011)",
        xes_path="data/raw/Hospital_log.xes.gz",
        agent_column="org:group",
        context_column="case:Age",
        role_mode="specialism",
        fit_months=7,
        holdout_months=3,
        subsample_fit=None,
        subsample_hold=None,
        queue_hold_max=200,
        terminal_prefixes=(),
    ),
}


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _resolve_xes(spec: DonorSpec) -> Path:
    p = ROOT / spec.xes_path if not Path(spec.xes_path).is_absolute() else Path(spec.xes_path)
    if p.exists():
        return p
    if str(p).endswith(".gz"):
        alt = Path(str(p)[:-3])
        if alt.exists():
            return alt
    if p.suffix == ".xes":
        gz = Path(str(p) + ".gz")
        if gz.exists():
            return gz
    raise FileNotFoundError(f"Нет файла лога для {spec.id}: {p}")


def _spec_from_custom(raw: dict[str, Any]) -> DonorSpec:
    tp = raw.get("terminal_prefixes")
    if tp is None:
        terminal = (
            "A_CANCELLED",
            "A_DECLINED",
            "A_APPROVED",
            "A_REGISTERED",
        )
    else:
        terminal = tuple(str(x) for x in tp)
    return DonorSpec(
        id=str(raw["id"]),
        label=str(raw.get("label") or raw["id"]),
        xes_path=str(raw.get("xes_path") or ""),
        agent_column=str(raw.get("agent_column") or "org:resource"),
        context_column=str(raw.get("context_column") or ""),
        role_mode=str(raw.get("role_mode") or "activity_prefix"),
        fit_months=int(raw.get("fit_months") or 3),
        holdout_months=int(raw.get("holdout_months") or 2),
        time_filter_from=raw.get("time_filter_from"),
        subsample_fit=raw.get("subsample_fit", 4000),
        subsample_hold=raw.get("subsample_hold", 2000),
        max_iter=int(raw.get("max_iter") or 250),
        queue_hold_max=int(raw.get("queue_hold_max") or 800),
        terminal_prefixes=terminal,
        origin=str(raw.get("origin") or "upload"),
        format=str(raw.get("format") or "xes"),
        mapping=raw.get("mapping"),
        assumption=bool(raw.get("assumption")),
        sla_hours=float(raw.get("sla_hours") or 72.0),
    )


def resolve_donor_spec(donor_id: str) -> DonorSpec:
    """Встроенный DONORS или запись из registry upload/greenfield."""
    if donor_id in DONORS:
        return DONORS[donor_id]
    custom = donor_registry.load_custom_donors()
    if donor_id not in custom:
        raise KeyError(f"Неизвестный донор: {donor_id}")
    return _spec_from_custom(custom[donor_id])


def list_donors() -> list[dict]:
    """Список сетов: демо (открытые логи) и проекты пользователя — не «вшитые фичи» UI."""
    out = []
    for d in DONORS.values():
        try:
            path = _resolve_xes(d)
            available = path.exists()
        except FileNotFoundError:
            available = False
        out.append(
            {
                "id": d.id,
                "label": d.label,
                "available": available,
                "agent_column": d.agent_column,
                "role_mode": d.role_mode,
                "origin": "builtin",
                "kind": "demo",
                "demo": True,
                "format": d.format,
                "badge": "Демо",
                "subtitle": "Открытые учебные данные (не данные заказчика)",
            }
        )
    for raw in donor_registry.load_custom_donors().values():
        d = _spec_from_custom(raw)
        origin = d.origin if d.origin in ("upload", "greenfield") else "upload"
        available = False
        if d.xes_path:
            try:
                available = _resolve_xes(d).exists()
            except FileNotFoundError:
                available = False
        elif origin == "greenfield":
            available = True
        out.append(
            {
                "id": d.id,
                "label": d.label,
                "available": available,
                "agent_column": d.agent_column,
                "role_mode": d.role_mode,
                "origin": origin,
                "kind": "project",
                "demo": False,
                "format": d.format,
                "badge": "Загрузка" if origin == "upload" else "Черновик",
                "subtitle": (
                    "Ваш файл (CSV/XES)"
                    if origin == "upload"
                    else "Greenfield без лога — допущения"
                ),
            }
        )
    return out


class OrgModelStore:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (ROOT / "data" / "derived" / "ui_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._design: dict[str, dict] = {}
        self._models: dict[str, dict] = {}
        self._runtime: dict[str, dict] = {}

    def cache_path(self, donor_id: str) -> Path:
        return self.cache_dir / f"org_model_v{ORG_MODEL_CACHE_VER}_{donor_id}.json"

    def get_design(self, donor_id: str) -> dict:
        if donor_id not in self._design:
            path = self.cache_dir / f"design_{donor_id}.json"
            if path.exists():
                self._design[donor_id] = json.loads(path.read_text(encoding="utf-8"))
            else:
                self._design[donor_id] = {
                    "roles": [],
                    "agents": [],
                    "edges": [],
                    "capacities": {},
                }
        return self._design[donor_id]

    def put_design(self, donor_id: str, payload: dict) -> dict:
        design = {
            "roles": payload.get("roles", []),
            "agents": payload.get("agents", []),
            "edges": payload.get("edges", []),
            "capacities": payload.get("capacities", {}),
        }
        self._design[donor_id] = design
        path = self.cache_dir / f"design_{donor_id}.json"
        path.write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
        # invalidate merged model cache in memory
        self._models.pop(donor_id, None)
        return design

    def build(
        self,
        donor_id: str,
        *,
        force: bool = False,
        with_queue: bool = True,
        max_queue_cases: int | None = None,
        on_progress: Any = None,
    ) -> dict:
        def prog(pct: int, stage: str, detail: str = "") -> None:
            if on_progress:
                on_progress(pct, stage, detail)

        def _ok(m: dict) -> bool:
            return (not with_queue) or m.get("queue_slices") is not None

        if not force and donor_id in self._models and _ok(self._models[donor_id]):
            prog(100, "Из памяти", "кэш в RAM")
            return self._models[donor_id]
        cache = self.cache_path(donor_id)
        if not force and cache.exists():
            prog(10, "Чтение кэша", cache.name)
            model = json.loads(cache.read_text(encoding="utf-8"))
            if _ok(model):
                model = self._merge_design(donor_id, model)
                self._models[donor_id] = model
                prog(100, "Из кэша", "без пересчёта")
                return model

        if donor_id not in DONORS and donor_id not in donor_registry.load_custom_donors():
            raise KeyError(f"Неизвестный донор: {donor_id}")
        spec = resolve_donor_spec(donor_id)
        model = self._build_from_log(
            spec,
            with_queue=with_queue,
            max_queue_cases=max_queue_cases,
            on_progress=on_progress,
        )
        # на диск пишем только полную модель (с очередью), чтобы UI не залипал на incomplete cache
        if with_queue and model.get("queue_slices") is not None:
            prog(98, "Сохранение кэша", "")
            cache.write_text(json.dumps(model, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        elif not cache.exists():
            cache.write_text(json.dumps(model, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        model = self._merge_design(donor_id, model)
        self._models[donor_id] = model
        prog(100, "Готово", f"{model.get('build_wall_sec')} с")
        return model

    def _merge_design(self, donor_id: str, model: dict) -> dict:
        design = self.get_design(donor_id)
        out = json.loads(json.dumps(model))  # deep copy via json
        agents_by_id = {a["id"]: a for a in out.get("agents", [])}
        roles_by_id = {r["id"]: r for r in out.get("roles", [])}

        for role in design.get("roles", []):
            rid = str(role["id"])
            if rid not in roles_by_id:
                roles_by_id[rid] = {
                    "id": rid,
                    "label": role.get("label", rid),
                    "n_agents": 0,
                    "origin": "manual",
                }
            else:
                roles_by_id[rid]["origin"] = "hybrid" if roles_by_id[rid].get("origin") == "log" else "manual"
                if role.get("label"):
                    roles_by_id[rid]["label"] = role["label"]

        for ag in design.get("agents", []):
            aid = str(ag["id"])
            if aid in agents_by_id:
                agents_by_id[aid]["origin"] = "hybrid"
                if ag.get("role_id"):
                    agents_by_id[aid]["role_id"] = ag["role_id"]
                if "capacity" in ag:
                    agents_by_id[aid]["capacity"] = int(ag["capacity"])
            else:
                agents_by_id[aid] = {
                    "id": aid,
                    "role_id": ag.get("role_id", "manual"),
                    "n_events": int(ag.get("n_events", 0)),
                    "stuck_frac": None,
                    "exclusive_actions": [],
                    "capacity": int(ag.get("capacity", 1)),
                    "origin": "manual",
                }

        for aid, cap in (design.get("capacities") or {}).items():
            if aid in agents_by_id:
                agents_by_id[aid]["capacity"] = int(cap)
                if agents_by_id[aid].get("origin") == "log":
                    agents_by_id[aid]["origin"] = "hybrid"

        edge_keys = {(e["from_agent"], e["to_agent"]) for e in out.get("edges", [])}
        for e in design.get("edges", []):
            key = (str(e["from_agent"]), str(e["to_agent"]))
            if key not in edge_keys:
                out.setdefault("edges", []).append(
                    {
                        "from_agent": key[0],
                        "to_agent": key[1],
                        "weight": float(e.get("weight", 1.0)),
                        "origin": "manual",
                    }
                )
                edge_keys.add(key)

        out["roles"] = list(roles_by_id.values())
        out["agents"] = list(agents_by_id.values())
        # recount role n_agents
        counts: dict[str, int] = {}
        for a in out["agents"]:
            counts[a["role_id"]] = counts.get(a["role_id"], 0) + 1
        for r in out["roles"]:
            r["n_agents"] = counts.get(r["id"], 0)

        origins = {a.get("origin") for a in out["agents"]}
        if "manual" in origins and "log" in origins or "hybrid" in origins:
            out["origin"] = "hybrid"
        elif origins == {"manual"}:
            out["origin"] = "manual"
        else:
            out["origin"] = out.get("origin", "log")
        return out

    def _build_from_log(
        self,
        spec: DonorSpec,
        *,
        with_queue: bool,
        max_queue_cases: int | None,
        on_progress: Any = None,
    ) -> dict:
        def prog(pct: int, stage: str, detail: str = "") -> None:
            if on_progress:
                on_progress(pct, stage, detail)

        t0 = time.perf_counter()

        # greenfield без файла — пустая ручная модель (design API)
        if spec.origin == "greenfield":
            has_file = bool(spec.xes_path) and (
                (ROOT / spec.xes_path).exists()
                if not Path(spec.xes_path).is_absolute()
                else Path(spec.xes_path).exists()
            )
            if not has_file:
                wall = time.perf_counter() - t0
                prog(100, "Greenfield без лога", "только design")
                return {
                    "donor_id": spec.id,
                    "label": spec.label,
                    "origin": "manual",
                    "donor_origin": "greenfield",
                    "roles": [],
                    "agents": [],
                    "rules": [],
                    "edges": [],
                    "metrics": None,
                    "schema_version": ORG_MODEL_CACHE_VER,
                    "queue_slices": None,
                    "flow_sample": [],
                    "split_meta": {},
                    "ingest": None,
                    "build_wall_sec": round(wall, 2),
                    "honesty": {
                        "proven": [],
                        "not_proven": [
                            "модель без event log — только ручной design",
                            "календарь смен и SLA",
                            "живой коннектор SAP/1С/Битрикс",
                        ],
                    },
                }

        prog(5, "Загрузка лога", spec.xes_path)
        df = self._load_event_df(spec)
        report = ingest_report(df, spec.agent_column or "org:resource")
        prog(12, "Отчёт ingest", f"{report.get('n_events')} событий, {report.get('n_cases')} кейсов")
        if spec.time_filter_from:
            df, _ = filter_event_table(df, time_from=spec.time_filter_from)

        fit_m, hold_m = spec.fit_months, spec.holdout_months
        span = float((report or {}).get("span_days") or 0)
        if span >= 300 and spec.origin in ("upload", "greenfield", "builtin"):
            # протокол 7+3 при достаточном горизонте
            fit_m, hold_m = max(fit_m, 7), max(hold_m, 3)
        prog(18, "Разделение fit/hold", f"{fit_m}+{hold_m} мес")
        fit, hold, split_meta = fit_holdout_split(
            df, fit_months=fit_m, holdout_months=hold_m
        )
        split_meta["requested_fit_months"] = fit_m
        split_meta["requested_holdout_months"] = hold_m
        split_meta["span_days"] = span
        if span < 300:
            split_meta["window_warning"] = "лог короче года — окно урезано относительно цели 7+3"
        # subsample только для DES-очереди; политика и метрики — на полном fit/hold
        fit_q, hold_q = fit, hold
        if spec.subsample_fit or spec.subsample_hold:
            fit_q, hold_q, smeta = subsample_case_split(
                fit,
                hold,
                fit_max=spec.subsample_fit,
                hold_max=spec.subsample_hold,
                seed=42,
            )
            split_meta = {**split_meta, **smeta, "policy_on_full_split": True}

        ctx = spec.context_column or None
        agent_col = spec.agent_column or None
        prep = {"agent_col": agent_col, "context_col": ctx}

        prog(28, "Обучение счётчиков", f"fit={len(fit)} строк")
        counts_pol = train_count_policies(
            fit,
            agent_col=agent_col or "org:resource",
            context_col=ctx,
            role_mode=spec.role_mode,
        )
        prog(38, "Holdout: счётчики", f"hold={len(hold)} строк")
        ns_counts = next_step_accuracy_counts(counts_pol, hold, **prep)

        prog(48, "Обучение softmax", f"max_iter={spec.max_iter}")
        pol = train_softmax_policies(
            fit,
            max_iter=spec.max_iter,
            agent_col=agent_col,
            context_col=ctx,
            role_mode=spec.role_mode,
        )
        prog(58, "Holdout: softmax", "")
        ns_sm = next_step_accuracy(pol, hold, **prep)

        ce_c = ns_counts.get("cross_entropy") or 1e9
        ce_s = ns_sm.get("cross_entropy") or 1e9
        # как в диагностике: метрики победителя по CE; симуляция/handover — softmax-бандл
        if ce_s + 1e-6 < ce_c:
            metrics = {**ns_sm, "policy_kind": "softmax"}
        else:
            metrics = {**ns_counts, "policy_kind": "counts"}

        prog(68, "Диагност (застревание / правила)", "")
        lm = diagnose_local_minima(
            fit,
            agent_col=spec.agent_column or "org:resource",
            context_col=ctx,
            role_mode=spec.role_mode,
            amount_bin_edges=pol.amount_bin_edges,
        )

        role_counts: dict[str, int] = {}
        agents = []
        rules = []
        for rec in lm["agents"]:
            aid = str(rec["agent_id"])
            if is_ghost_agent(aid):
                continue
            role = str(rec.get("role_id", "UNKNOWN"))
            role_counts[role] = role_counts.get(role, 0) + 1
            exclusives = [
                {"action": x["action"], "share": x["share"], "agent_n": x["agent_n"]}
                for x in (rec.get("exclusive_frequent_actions") or [])[:8]
            ]
            agents.append(
                {
                    "id": aid,
                    "role_id": role,
                    "n_events": int(rec["n_events"]),
                    "stuck_frac": _safe_float(rec.get("stuck_event_fraction")),
                    "exclusive_actions": exclusives,
                    "capacity": 1,
                    "origin": "log",
                    "n_distinct_actions": int(rec.get("n_distinct_actions", 0)),
                    "mean_H_bits": _safe_float(rec.get("mean_H_bits_typical_input")),
                }
            )
            for rule in (rec.get("max_local_rules") or [])[:6]:
                rules.append(
                    {
                        "agent_id": aid,
                        "input": rule["input"],
                        "top1_action": rule["top1_action"],
                        "top1_mass": float(rule["top1_mass"]),
                        "support": int(rule["support"]),
                    }
                )

        roles = [
            {"id": rid, "label": rid, "n_agents": n, "origin": "log"}
            for rid, n in sorted(role_counts.items(), key=lambda x: -x[1])
        ]

        edges = []
        for src, dist in pol.handover_probs.items():
            if is_ghost_agent(src):
                continue
            for dst, w in dist.items():
                if is_ghost_agent(dst) or w <= 0:
                    continue
                if float(w) < 0.02:
                    continue
                edges.append(
                    {
                        "from_agent": str(src),
                        "to_agent": str(dst),
                        "weight": float(w),
                        "origin": "log",
                    }
                )
        edges.sort(key=lambda e: -e["weight"])
        edges = edges[:400]

        # sample case paths for flow animation
        prog(82, "Сэмпл потоков", "")
        flow_sample = _sample_case_paths(hold_q, n_cases=24, max_steps=12)

        queue_slices = None
        if with_queue:
            prog(88, "Симуляция очередей ×1 / ×2 / слот+1", "DES — самый долгий этап")
            q_hold = hold_q
            qmax = max_queue_cases if max_queue_cases is not None else spec.queue_hold_max
            if qmax and hold_q["case:concept:name"].nunique() > qmax:
                keep = (
                    hold_q.groupby("case:concept:name", as_index=False)
                    .first()
                    .sample(n=qmax, random_state=42)["case:concept:name"]
                )
                q_hold = hold_q[hold_q["case:concept:name"].isin(keep)]
            queue_slices = self._run_queue_slices(q_hold, pol, spec)
            self._runtime[spec.id] = {"hold": q_hold, "pol": pol, "spec": spec}
        else:
            self._runtime[spec.id] = {"hold": hold_q, "pol": pol, "spec": spec}

        wall = time.perf_counter() - t0
        return {
            "donor_id": spec.id,
            "label": spec.label,
            "origin": "log",
            "roles": roles,
            "agents": agents,
            "rules": rules,
            "edges": edges,
            "metrics": {
                "next_step": _safe_float(metrics.get("accuracy")),
                "top3": _safe_float(metrics.get("top3_accuracy")),
                "ce": _safe_float(metrics.get("cross_entropy")),
                "n": int(metrics.get("n") or 0),
                "policy_kind": metrics.get("policy_kind"),
                "counts_next_step": _safe_float(ns_counts.get("accuracy")),
                "softmax_next_step": _safe_float(ns_sm.get("accuracy")),
                "counts_top3": _safe_float(ns_counts.get("top3_accuracy")),
                "softmax_top3": _safe_float(ns_sm.get("top3_accuracy")),
            },
            "schema_version": ORG_MODEL_CACHE_VER,
            "queue_slices": queue_slices,
            "flow_sample": flow_sample,
            "ingest": report,
            "donor_origin": spec.origin,
            "assumption": bool(spec.assumption or spec.origin == "greenfield"),
            "sla_hours": spec.sla_hours,
            "split_meta": {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in split_meta.items()},
            "build_wall_sec": round(wall, 2),
            "honesty": {
                "proven": [
                    "предсказание следующего шага на holdout не случайно",
                    "локальные правила агентов из лога",
                    "очереди растут при ×2 потоке",
                    "Σdt кейса из DES — оценка ожидания+обслуживания в очереди",
                ],
                "not_proven": [
                    "календарь смен как в HR (если не загружен — допущение)",
                    "календарный wall-clock ERP (Σdt ≠ SAP/1С)",
                    "живой коннектор SAP/1С/Битрикс",
                ],
            },
        }

    def _load_event_df(self, spec: DonorSpec) -> pd.DataFrame:
        from orgtwin.ingest.adapters import normalize_event_table

        path = _resolve_xes(spec)
        fmt = (spec.format or "xes").lower()
        if fmt == "csv" or path.suffix.lower() == ".csv":
            df = CsvEventsAdapter(path, mapping=spec.mapping).load()
            return normalize_event_table(df, agent_col=spec.agent_column or "org:resource")
        return XesAdapter(path, agent_col=spec.agent_column or None).load()

    def register_upload(
        self,
        *,
        donor_id: str,
        label: str,
        content: bytes,
        filename: str,
        agent_column: str = "org:resource",
        context_column: str = "",
        role_mode: str = "activity_prefix",
        fit_months: int = 3,
        holdout_months: int = 2,
        mapping: dict[str, str] | None = None,
        fmt: str | None = None,
        origin: str = "upload",
    ) -> dict:
        """
        Сохранить файл в data/uploads/{id}/, записать registry, сбросить кэш.
        Возвращает нормализованный spec (+ ingest при успешной загрузке таблицы).
        """
        if donor_id in DONORS:
            raise ValueError(f"id {donor_id} занят встроенным донором")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]{0,63}", donor_id):
            raise ValueError("donor_id: латиница/цифры/_/-, 1–64 символа")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError(
                f"Файл слишком большой: {len(content)} байт (лимит {MAX_UPLOAD_BYTES})"
            )
        if not content:
            raise ValueError("Пустой файл")

        safe_name = Path(filename).name
        if not safe_name or safe_name in (".", ".."):
            raise ValueError("Некорректное имя файла")

        lower = safe_name.lower()
        if fmt is None:
            if lower.endswith(".csv"):
                fmt = "csv"
            elif lower.endswith(".xes") or lower.endswith(".xes.gz"):
                fmt = "xes"
            else:
                raise ValueError("Ожидается .xes / .xes.gz / .csv")
        fmt = fmt.lower()
        if fmt not in ("xes", "csv"):
            raise ValueError("format: xes|csv")

        donor_dir = UPLOAD_ROOT / donor_id
        donor_dir.mkdir(parents=True, exist_ok=True)
        dest = donor_dir / safe_name
        dest.write_bytes(content)

        rel = f"data/uploads/{donor_id}/{safe_name}"
        spec_dict = donor_registry.save_custom_donor(
            {
                "id": donor_id,
                "label": label or donor_id,
                "xes_path": rel,
                "agent_column": agent_column,
                "context_column": context_column,
                "role_mode": role_mode,
                "fit_months": fit_months,
                "holdout_months": holdout_months,
                "origin": origin if origin in ("upload", "greenfield") else "upload",
                "format": fmt,
                "mapping": mapping,
            }
        )

        self._models.pop(donor_id, None)
        self._runtime.pop(donor_id, None)
        cache = self.cache_path(donor_id)
        if cache.exists():
            cache.unlink()

        report: dict | None
        try:
            spec = _spec_from_custom(spec_dict)
            df = self._load_event_df(spec)
            report = ingest_report(df, agent_column or "org:resource")
        except Exception as e:
            report = {"error": str(e)}

        return {**spec_dict, "ingest": report}

    def delete_upload(self, donor_id: str) -> bool:
        """Удалить пользовательский донор (не трогает builtin DONORS)."""
        if donor_id in DONORS:
            raise ValueError(f"Нельзя удалить встроенный донор {donor_id}")
        ok = donor_registry.delete_custom_donor(donor_id)
        self._models.pop(donor_id, None)
        self._runtime.pop(donor_id, None)
        self._design.pop(donor_id, None)
        cache = self.cache_path(donor_id)
        if cache.exists():
            cache.unlink()
        design = self.cache_dir / f"design_{donor_id}.json"
        if design.exists():
            design.unlink()
        return ok

    def _run_queue_slices(self, hold: pd.DataFrame, pol, spec: DonorSpec) -> dict:
        if hold is None or hold.empty or "time:timestamp" not in hold.columns:
            empty = {
                "max_queue_any_real": 0,
                "bottleneck_agent": None,
                "top_agents": [],
                "n_events": 0,
                "n_cases": 0,
                "case_duration": {"p50_sec": None, "p90_sec": None, "mean_sec": None, "n": 0},
                "sla": {"sla_hours": spec.sla_hours, "n": 0, "breach_frac": None},
            }
            return {"x1": dict(empty), "x2": dict(empty), "x2_plus1": dict(empty)}
        cfg_base = ExperimentConfig(
            policy=PolicyConfig(terminal_prefixes=spec.terminal_prefixes),
            timing=TimingConfig(),
            sim=SimConfig(queue_mode=True, agent_capacity=1, max_steps_per_case=30, seed=42),
        )
        results = {}
        for mult, key in ((1.0, "x1"), (2.0, "x2")):
            cfg = ExperimentConfig(
                policy=cfg_base.policy,
                timing=cfg_base.timing,
                sim=SimConfig(
                    queue_mode=True,
                    input_flow_multiplier=mult,
                    agent_capacity=1,
                    max_steps_per_case=30,
                    seed=42,
                ),
            )
            sim = simulate_queue(hold, pol, cfg=cfg, drop_ghost_agents=True)
            top = _top_queues(sim)
            durs = getattr(sim, "case_durations_sec", None) or {}
            results[key] = {
                "max_queue_any_real": top[0][1] if top else 0,
                "bottleneck_agent": top[0][0] if top else None,
                "top_agents": [{"id": a, "max_queue": q} for a, q in top[:10]],
                "n_events": len(sim.events),
                "n_cases": sim.meta.get("n_cases"),
                "case_duration": duration_percentiles(durs),
                "sla": sla_metrics(durs, spec.sla_hours),
            }

        bottleneck = results["x2"].get("bottleneck_agent")
        overrides = {bottleneck: 2} if bottleneck else None
        cfg2 = ExperimentConfig(
            policy=cfg_base.policy,
            timing=cfg_base.timing,
            sim=SimConfig(
                queue_mode=True,
                input_flow_multiplier=2.0,
                agent_capacity=1,
                max_steps_per_case=30,
                seed=42,
            ),
        )
        sim_p = simulate_queue(
            hold, pol, cfg=cfg2, capacity_overrides=overrides, drop_ghost_agents=True
        )
        top_p = _top_queues(sim_p)
        before = None
        after = None
        if bottleneck:
            before = next((x["max_queue"] for x in results["x2"]["top_agents"] if x["id"] == bottleneck), None)
            after = dict(top_p).get(bottleneck, 0) if isinstance(dict(top_p), dict) else None
            # top_p is list of tuples
            after = next((q for a, q in top_p if a == bottleneck), 0)
        results["x2_plus1"] = {
            "max_queue_any_real": top_p[0][1] if top_p else 0,
            "bottleneck_agent": top_p[0][0] if top_p else None,
            "boosted_agent": bottleneck,
            "boosted_queue_before": before,
            "boosted_queue_after": after,
            "top_agents": [{"id": a, "max_queue": q} for a, q in top_p[:10]],
            "n_events": len(sim_p.events),
        }
        return results

    def ensure_runtime(self, donor_id: str) -> dict:
        if donor_id in self._runtime:
            return self._runtime[donor_id]
        # кэш JSON без runtime — пересоберём с очередью (заполнит _runtime)
        self.build(donor_id, force=True, with_queue=True)
        if donor_id not in self._runtime:
            raise RuntimeError(f"Не удалось подготовить runtime для {donor_id}")
        return self._runtime[donor_id]

    def run_whatif(
        self,
        donor_id: str,
        *,
        exclude_agents: list[str] | None = None,
        exclude_roles: list[str] | None = None,
        role_multipliers: dict[str, float] | None = None,
        global_multiplier: float = 1.0,
    ) -> dict:
        """Сценарий: без сотрудников/отделов и/или локальная нагрузка на отдел."""
        rt = self.ensure_runtime(donor_id)
        hold: pd.DataFrame = rt["hold"]
        pol = rt["pol"]
        spec: DonorSpec = rt["spec"]
        model = self.build(donor_id, with_queue=False)

        excluded: set[str] = set(exclude_agents or [])
        role_ex = set(exclude_roles or [])
        for a in model.get("agents", []):
            if a.get("role_id") in role_ex:
                excluded.add(str(a["id"]))

        # baseline ×1
        cfg1 = ExperimentConfig(
            policy=PolicyConfig(terminal_prefixes=spec.terminal_prefixes),
            timing=TimingConfig(),
            sim=SimConfig(
                queue_mode=True,
                input_flow_multiplier=1.0,
                agent_capacity=1,
                max_steps_per_case=30,
                seed=42,
            ),
        )
        base = simulate_queue(hold, pol, cfg=cfg1, drop_ghost_agents=True)
        base_top = _top_queues(base)

        cfg = ExperimentConfig(
            policy=PolicyConfig(terminal_prefixes=spec.terminal_prefixes),
            timing=TimingConfig(),
            sim=SimConfig(
                queue_mode=True,
                input_flow_multiplier=float(global_multiplier),
                agent_capacity=1,
                max_steps_per_case=30,
                seed=42,
            ),
        )
        sim = simulate_queue(
            hold,
            pol,
            cfg=cfg,
            drop_ghost_agents=True,
            exclude_agents=excluded,
            role_flow_multipliers=role_multipliers or None,
        )
        top = _top_queues(sim)
        return {
            "donor_id": donor_id,
            "exclude_agents": sorted(excluded),
            "exclude_roles": sorted(role_ex),
            "role_multipliers": role_multipliers or {},
            "global_multiplier": global_multiplier,
            "baseline": {
                "max_queue_any_real": base_top[0][1] if base_top else 0,
                "bottleneck_agent": base_top[0][0] if base_top else None,
                "top_agents": [{"id": a, "max_queue": q} for a, q in base_top[:10]],
            },
            "scenario": {
                "max_queue_any_real": top[0][1] if top else 0,
                "bottleneck_agent": top[0][0] if top else None,
                "top_agents": [{"id": a, "max_queue": q} for a, q in top[:10]],
                "n_cases": sim.meta.get("n_cases"),
            },
            "delta_max_queue": (top[0][1] if top else 0) - (base_top[0][1] if base_top else 0),
        }


def _top_queues(sim) -> list[tuple[str, int]]:
    rows = []
    for a, s in sim.meta.get("queue_stats", {}).items():
        if is_ghost_agent(a):
            continue
        rows.append((a, int(s["max_queue_length"])))
    rows.sort(key=lambda x: -x[1])
    return rows


def _sample_case_paths(hold: pd.DataFrame, n_cases: int = 24, max_steps: int = 12) -> list[dict]:
    cases = hold["case:concept:name"].drop_duplicates().tolist()
    rng = np.random.default_rng(42)
    if len(cases) > n_cases:
        cases = list(rng.choice(cases, size=n_cases, replace=False))
    paths = []
    for cid in cases:
        g = hold[hold["case:concept:name"] == cid].sort_values("time:timestamp")
        agents = []
        acts = []
        for _, row in g.head(max_steps).iterrows():
            ag = str(row.get("org:resource", row.get("org:group", "UNKNOWN")))
            if is_ghost_agent(ag):
                continue
            agents.append(ag)
            acts.append(str(row.get("concept:name", "")))
        if len(agents) >= 2:
            paths.append({"case_id": str(cid), "agents": agents, "activities": acts})
    return paths
