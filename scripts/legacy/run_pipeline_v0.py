#!/usr/bin/env python3
"""Пайплайн v0: один донор BPIC2012 → DoF (Information+Action) → симуляция → score."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin.decompose.dof import decompose_org, degrees_of_freedom_report
from orgtwin.eval.score import evaluate
from orgtwin.ingest.xes_loader import fit_holdout_split, load_event_table
from orgtwin.sim.engine import simulate


def main() -> None:
    xes = ROOT / "data" / "raw" / "BPI_Challenge_2012.xes"
    derived = ROOT / "data" / "derived"
    reports = ROOT / "reports"
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    print("Загрузка XES…")
    df = load_event_table(xes)
    print(f"  событий={len(df)} кейсов={df['case:concept:name'].nunique()} агентов={df['org:resource'].nunique()}")

    # BPIC2012 ~5.5 мес → fit 3 / holdout 2 (пропорция как 7→3)
    fit, hold, split_meta = fit_holdout_split(df, fit_months=3, holdout_months=2)
    print(f"  split: fit_cases={split_meta['fit_cases']} hold_cases={split_meta['hold_cases']}")

    print("Декомпозиция Information+Action / нейроавтоматы…")
    graph = decompose_org(fit, donor_id="BPIC2012", min_agent_events=5)
    dof = degrees_of_freedom_report(graph)
    print(f"  автоматов={dof['n_automata']} ролей={list(dof['roles'])}")

    (derived / "dof_report.json").write_text(
        json.dumps(dof, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / "split_meta.json").write_text(
        json.dumps(split_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # краткий дамп мембран
    membranes = {
        role: {
            "sensors": info["sensor_keys"],
            "actions": info["action_names"],
            "n_automata": info["n_automata"],
            "shannon_upper_bits": info["shannon_upper_bits"],
        }
        for role, info in dof["roles"].items()
    }
    (derived / "membranes.json").write_text(
        json.dumps(membranes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # примеры локальных правил (топ-агенты)
    top_agents = sorted(graph.automata.values(), key=lambda a: a.event_count, reverse=True)[:5]
    rules_sample = {
        a.agent_id: {
            "role_id": a.role_id,
            "event_count": a.event_count,
            "n_rules": len(a.rules),
            "top_rules": [
                {
                    "action": r.action_name,
                    "when": r.condition_signature,
                    "p": round(r.probability, 4),
                    "n": r.count,
                }
                for r in sorted(a.rules, key=lambda x: -x.count)[:15]
            ],
        }
        for a in top_agents
    }
    (derived / "local_rules_sample.json").write_text(
        json.dumps(rules_sample, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Симуляция holdout…")
    sim = simulate(graph, hold, max_steps_per_case=40, seed=42)
    print(f"  sim_events={len(sim.events)} cases={len(sim.case_durations_sec)}")

    print("Оценка…")
    report = evaluate(hold, sim)
    (reports / "holdout_metrics.json").write_text(
        json.dumps(report.metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    weekly = pd_weekly(report)
    weekly.to_csv(reports / "weekly_actual_vs_pred.csv", index=True)

    md = render_markdown(split_meta, dof, report.metrics)
    (reports / "run_v0.md").write_text(md, encoding="utf-8")
    print(md)
    print("\nГотово → reports/run_v0.md")


def pd_weekly(report):
    import pandas as pd

    return pd.DataFrame({"actual": report.weekly_actual, "pred": report.weekly_pred})


def render_markdown(split_meta: dict, dof: dict, metrics: dict) -> str:
    roles_lines = []
    for role, info in dof["roles"].items():
        roles_lines.append(
            f"- **{role}**: автоматов={info['n_automata']}, "
            f"действий={info['n_actions']}, "
            f"H≤{info['shannon_upper_bits']:.2f} бит, "
            f"событий={info['total_events']}"
        )
    return f"""# Прогон v0 — BPIC2012 (один донор)

## Донор
- BPI Challenge 2012, один финансовый институт
- Fit/holdout: {split_meta['fit_months']}м / {split_meta['holdout_months']}м
- Fit: {split_meta['fit_cases']} кейсов, {split_meta['fit_events']} событий
- Holdout: {split_meta['hold_cases']} кейсов, {split_meta['hold_events']} событий

## Базис декомпозиции
- **Information** — атомы схемы ({dof['n_information_atoms']})
- **Action** — каталог мутаций ({dof['n_actions_catalog']})
- **Нейроавтоматы** — 1 `org:resource` = 1 экземпляр ({dof['n_automata']})
- Hand-over рёбер: {dof['n_handover_edges']}

## Роли / мембраны
{chr(10).join(roles_lines)}

## Holdout metrics
```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

## Замечание
BPIC2012 короче года (~5.5 мес), поэтому окно 3+2 вместо 7+3; логика протокола та же.
"""


if __name__ == "__main__":
    main()
