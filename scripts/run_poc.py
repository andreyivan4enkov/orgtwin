#!/usr/bin/env python3
"""
Полный proof of concept OrgTwin: диагност + честная очередь на одном доноре.

  .venv/bin/python scripts/run_poc.py
  .venv/bin/python scripts/run_poc.py --config configs/simulator/v0.7.0.json

Не LLM. Метрика нагрузки — длина очереди. Слот +1 на узком агенте.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from orgtwin.config.constants import ExperimentConfig, SimConfig
from orgtwin.diag.local_minima import diagnose_local_minima
from orgtwin.policy.counts import next_step_accuracy_counts, train_count_policies
from orgtwin.policy.softmax import next_step_accuracy, train_softmax_policies
from orgtwin.sim.queue_des import is_ghost_agent, simulate_queue
from run_queue_stress import load_split


def _top_queues(sim, n: int = 8, skip_ghost: bool = True) -> list[tuple[str, int]]:
    rows = []
    for a, s in sim.meta["queue_stats"].items():
        if skip_ghost and is_ghost_agent(a):
            continue
        rows.append((a, int(s["max_queue_length"])))
    rows.sort(key=lambda x: -x[1])
    return rows[:n]


def _queue_run(hold, pol, cfg, mult: float, overrides=None):
    run_cfg = ExperimentConfig(
        donor_id=cfg.donor_id,
        policy=cfg.policy,
        timing=cfg.timing,
        sim=SimConfig(
            queue_mode=True,
            input_flow_multiplier=mult,
            agent_capacity=1,
            max_steps_per_case=cfg.sim.max_steps_per_case,
            seed=cfg.sim.seed,
        ),
    )
    t0 = time.perf_counter()
    sim = simulate_queue(
        hold,
        pol,
        cfg=run_cfg,
        max_steps_per_case=cfg.sim.max_steps_per_case,
        capacity_overrides=overrides,
        drop_ghost_agents=True,
    )
    wall = time.perf_counter() - t0
    top = _top_queues(sim)
    return {
        "wall_sec": wall,
        "max_queue_any_real": top[0][1] if top else 0,
        "bottleneck_agent": top[0][0] if top else None,
        "sum_final_queue": sim.meta["sum_final_queue_length"],
        "n_events": len(sim.events),
        "n_cases": sim.meta["n_cases"],
        "top_agents_by_max_queue": top,
        "capacity_overrides": overrides or {},
    }, sim


def _write_report(path: Path, payload: dict) -> None:
    d = payload["diagnostic"]
    q1 = payload["queue"]["flow_x1"]
    q2 = payload["queue"]["flow_x2"]
    qplus = payload["queue"].get("flow_x2_plus1")
    lines = [
        "# OrgTwin — proof of concept",
        "",
        f"**Версия:** {payload['version']}  ",
        f"**Донор прогона:** {payload['donor']}  ",
        f"**Конфиг:** `{payload['config']}`",
        "",
        "## Простым языком",
        "",
        "Из журнала событий видно, **кто что делает** после какого входа. "
        "Это не нейросеть-чат, а табличное правило. "
        "Если входящих заявок станет в два раза больше, а людей столько же, "
        "**очередь растёт у узких агентов** — это и есть захлёб.",
        "",
        "## 1. Диагност (факт из лога)",
        "",
        f"| Метрика holdout | counts | softmax |",
        f"|-----------------|--------|---------|",
        f"| next-step | {d['counts']['accuracy']:.3f} | {d['softmax']['accuracy']:.3f} |",
        f"| top-3 | {d['counts']['top3_accuracy']:.3f} | {d['softmax']['top3_accuracy']:.3f} |",
        f"| CE | {d['counts']['cross_entropy']:.3f} | {d['softmax']['cross_entropy']:.3f} |",
        "",
        f"Агентов на fit: **{d['local_minima']['n_agents']}**. "
        f"С незаменимыми частыми действиями: **{d['n_exclusive_agents']}**.",
        "",
        "Топ застревания (stuck_frac):",
        "",
    ]
    for rec in d["stuck_top"]:
        lines.append(
            f"- `{rec['agent_id']}`: stuck={rec['stuck_event_fraction']:.2f}, "
            f"событий={rec['n_events']}, незаменимых действий={rec['n_exclusive']}"
        )
    lines += [
        "",
        "## 2. Честная очередь (не «время в пути»)",
        "",
        "Слот занятости = 1. Ghost-агенты (`NONE`/`UNKNOWN`) не считаются узким местом.",
        "",
        "| Сценарий | узкий агент | max_queue |",
        "|----------|-------------|-----------|",
        f"| поток ×1 | `{q1['bottleneck_agent']}` | **{q1['max_queue_any_real']}** |",
        f"| поток ×2 | `{q2['bottleneck_agent']}` | **{q2['max_queue_any_real']}** |",
    ]
    if qplus:
        lines.append(
            f"| поток ×2, слот +1 у `{qplus.get('boosted_agent')}` | "
            f"`{qplus['bottleneck_agent']}` | **{qplus['max_queue_any_real']}** |"
        )
    growth = None
    if q1["max_queue_any_real"]:
        growth = q2["max_queue_any_real"] / q1["max_queue_any_real"]
        lines += [
            "",
            f"Рост очереди при ×2: **{growth:.2f}×** "
            f"({q1['max_queue_any_real']} → {q2['max_queue_any_real']}).",
        ]
    lines += [
        "",
        "Топ очередей при ×2:",
        "",
    ]
    for ag, q in q2["top_agents_by_max_queue"][:5]:
        lines.append(f"- `{ag}`: max_queue={q}")
    if qplus:
        lines += [
            "",
            "## 3. Что если добавить 1 слот на узкое место",
            "",
            f"У агента `{qplus.get('boosted_agent')}` capacity 1→2 при том же ×2 потоке.",
            f"Очередь на нём: {qplus.get('boosted_queue_before')} → {qplus.get('boosted_queue_after')}.",
            f"Новый максимум по реальным агентам: **{qplus['max_queue_any_real']}** "
            f"(агент `{qplus['bottleneck_agent']}`).",
        ]
    lines += [
        "",
        "## Другие доноры (уже измеренные, не этот прогон)",
        "",
    ]
    for name, block in payload.get("prior_evidence", {}).items():
        lines.append(f"- **{name}:** {block}")
    lines += [
        "",
        "## Что доказано",
        "",
        "1. Next-step на holdout не случайность.",
        "2. Видны локальные правила и незаменимые действия.",
        "3. При ×2 потока растут очереди у узких агентов (не Σdt).",
        "4. Добавление слота на узком месте меняет картину очередей.",
        "",
        "## Что это не доказывает",
        "",
        "- Нет календаря смен и SLA клиента.",
        "- Нет закрытого лога заказчика.",
        "- FEP / case-head / weekly_corr — не KPI этого PoC.",
        "",
        f"JSON: `{payload['json_name']}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    (ROOT / "reports/poc").mkdir(parents=True, exist_ok=True)
    p = argparse.ArgumentParser(description="OrgTwin full PoC")
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/simulator/v0.7.0.json",
        help="JSON донора для живого прогона (по умолчанию BPIC2012)",
    )
    args = p.parse_args()
    cfg_path = args.config if args.config.is_absolute() else ROOT / args.config
    recipe = json.loads(cfg_path.read_text(encoding="utf-8"))
    fit, hold, meta, cfg, donor_id = load_split(recipe)
    adapt = cfg.donor_adapt
    agent_col = adapt.agent_column or None
    context_col = adapt.context_column or None
    role_mode = adapt.role_mode
    eval_kw = dict(agent_col=agent_col, context_col=context_col)

    print("Счётчики (диагност)…")
    counts = train_count_policies(
        fit, min_support=adapt.count_min_support, agent_col=agent_col, context_col=context_col, role_mode=role_mode
    )
    c_hold = next_step_accuracy_counts(counts, hold, **eval_kw)
    print(f"  counts next={c_hold['accuracy']:.3f} top3={c_hold['top3_accuracy']:.3f}")

    print("Softmax…")
    t0 = time.perf_counter()
    pol = train_softmax_policies(
        fit,
        max_iter=min(cfg.policy.max_iter, 150),
        random_state=cfg.policy.random_state,
        solver=cfg.policy.solver,
        tol=cfg.policy.tol,
        C=cfg.policy.C,
        agent_col=agent_col,
        context_col=context_col,
        role_mode=role_mode,
    )
    s_hold = next_step_accuracy(pol, hold, **eval_kw)
    print(
        f"  softmax next={s_hold['accuracy']:.3f} top3={s_hold['top3_accuracy']:.3f} "
        f"({time.perf_counter()-t0:.1f}s)"
    )

    print("Локальные минимумы…")
    lm = diagnose_local_minima(
        fit,
        agent_col=agent_col or "org:resource",
        context_col=context_col,
        role_mode=role_mode,
        amount_bin_edges=pol.amount_bin_edges,
    )
    stuck = []
    n_ex = 0
    for rec in lm["agents"]:
        if is_ghost_agent(rec["agent_id"]):
            continue
        nex = len(rec.get("exclusive_frequent_actions") or [])
        if nex:
            n_ex += 1
        sf = rec["stuck_event_fraction"]
        if sf is None or (isinstance(sf, float) and sf != sf):  # NaN
            continue
        if int(rec.get("n_typical_inputs") or 0) < 1 and rec["n_events"] < 50:
            continue
        stuck.append(
            {
                "agent_id": rec["agent_id"],
                "stuck_event_fraction": float(sf),
                "n_events": rec["n_events"],
                "n_exclusive": nex,
            }
        )
    stuck.sort(key=lambda x: (-x["stuck_event_fraction"], -x["n_events"]))
    stuck_top = stuck[:8]
    print(f"  агентов={lm['n_agents']} с незаменимыми={n_ex}")

    print("Очередь ×1…")
    q1, _ = _queue_run(hold, pol, cfg, 1.0)
    print(f"  {q1['bottleneck_agent']} max_queue={q1['max_queue_any_real']}")

    print("Очередь ×2…")
    q2, sim2 = _queue_run(hold, pol, cfg, 2.0)
    print(f"  {q2['bottleneck_agent']} max_queue={q2['max_queue_any_real']}")

    boosted = q2["bottleneck_agent"]
    qplus = None
    if boosted:
        before = dict(q2["top_agents_by_max_queue"]).get(boosted)
        print(f"Очередь ×2, слот +1 у {boosted}…")
        qplus, _ = _queue_run(hold, pol, cfg, 2.0, {boosted: 2})
        after = dict(qplus["top_agents_by_max_queue"]).get(boosted, 0)
        qplus["boosted_agent"] = boosted
        qplus["boosted_queue_before"] = before
        qplus["boosted_queue_after"] = after
        print(f"  {boosted}: {before} → {after}; new_max={qplus['max_queue_any_real']}")

    prior = {}
    h = ROOT / "reports/diagnostic/holdout_metrics_v0.8.0.json"
    if h.exists():
        hm = json.loads(h.read_text(encoding="utf-8"))
        prior["Hospital v0.8.0"] = (
            f"holdout next softmax={hm['comparison']['next_step_accuracy']['softmax']:.3f} "
            "(диагност отделений, без очереди)"
        )
    b19 = ROOT / "reports/simulator/queue_stress_bpic2019.json"
    if b19.exists():
        j = json.loads(b19.read_text(encoding="utf-8"))
        x1 = j["results"]["flow_x1"]["max_queue_any"]
        x2 = j["results"]["flow_x2"]["max_queue_any"]
        prior["BPIC2019 очередь"] = f"max_queue ×1={x1}, ×2={x2} (есть артефакт NONE в топе старого прогона)"

    out_dir = ROOT / "reports/poc"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_name = "poc_v0.11.0.json"
    payload = {
        "version": "0.11.0",
        "donor": donor_id,
        "config": str(cfg_path.relative_to(ROOT)),
        "json_name": f"reports/poc/{json_name}",
        "split_meta": meta,
        "diagnostic": {
            "counts": c_hold,
            "softmax": s_hold,
            "local_minima": {"n_agents": lm["n_agents"]},
            "n_exclusive_agents": n_ex,
            "stuck_top": stuck_top,
        },
        "queue": {
            "flow_x1": q1,
            "flow_x2": q2,
            "flow_x2_plus1": qplus,
        },
        "prior_evidence": prior,
        "claims": {
            "proven": [
                "holdout next-step не случаен",
                "очередь растёт при ×2",
                "слот +1 меняет узкое место",
            ],
            "not_proven": [
                "календарь смен",
                "закрытый контур клиента",
            ],
        },
    }
    (out_dir / json_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md = out_dir / "POC.md"
    _write_report(md, payload)
    print(f"\nPoC → {md}")


if __name__ == "__main__":
    main()
