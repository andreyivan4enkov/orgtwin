#!/usr/bin/env python3
"""
Пайплайн v1: организм BPIC2012 → Information/Action → softmax-политики →
прунинг мембран → симуляция → holdout (в т.ч. next-step).

Классика: multinomial logistic (softmax), CE + λH, усреднение через agent one-hot
в одном пространстве с ролевой маской мембраны.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin.decompose.dof import degrees_of_freedom_report
from orgtwin.eval.score import evaluate
from orgtwin.ingest.xes_loader import fit_holdout_split, load_event_table
from orgtwin.policy.softmax import prune_membrane_actions, train_softmax_policies
from orgtwin.sim.engine import build_org_from_policy, simulate


def main() -> None:
    xes = ROOT / "data" / "raw" / "BPI_Challenge_2012.xes"
    derived = ROOT / "data" / "derived"
    reports = ROOT / "reports"
    derived.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    print("Загрузка XES…")
    df = load_event_table(xes)
    print(
        f"  событий={len(df)} кейсов={df['case:concept:name'].nunique()} "
        f"агентов={df['org:resource'].nunique()}"
    )

    fit, hold, split_meta = fit_holdout_split(df, fit_months=3, holdout_months=2)
    print(f"  split: fit_cases={split_meta['fit_cases']} hold_cases={split_meta['hold_cases']}")

    print("Обучение softmax-политик (Information → Action)…")
    policy = train_softmax_policies(fit, lambda_entropy=0.05, max_iter=250)
    print(
        f"  fit acc={policy.train_metrics['fit_action_accuracy']:.3f} "
        f"CE={policy.train_metrics['cross_entropy']:.3f} "
        f"F≈{policy.train_metrics['free_energy_proxy']:.3f}"
    )

    print("Прунинг мембран (редкие Action)…")
    prune_info = prune_membrane_actions(policy, fit, lambda_entropy=0.05, min_support=30)
    (derived / "membrane_prune.json").write_text(
        json.dumps(prune_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Сборка OrgGraph / нейроавтоматов…")
    graph = build_org_from_policy(fit, policy, donor_id="BPIC2012")
    dof = degrees_of_freedom_report(graph)
    print(f"  автоматов={dof['n_automata']} ролей={list(dof['roles'])}")

    (derived / "dof_report.json").write_text(
        json.dumps(dof, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / "split_meta.json").write_text(
        json.dumps(split_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (derived / "train_metrics.json").write_text(
        json.dumps(policy.train_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    membranes = {
        role: {
            "sensors": info["sensor_keys"],
            "n_actions": info["n_actions"],
            "n_automata": info["n_automata"],
            "shannon_upper_bits": info["shannon_upper_bits"],
            "action_names": info["action_names"],
        }
        for role, info in dof["roles"].items()
    }
    (derived / "membranes.json").write_text(
        json.dumps(membranes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Симуляция holdout (календарные timestamps)…")
    sim = simulate(graph, hold, policy=policy, max_steps_per_case=40, seed=42)
    print(f"  sim_events={len(sim.events)} cases={len(sim.case_durations_sec)}")

    print("Оценка…")
    report = evaluate(hold, sim, policy=policy)
    (reports / "holdout_metrics_v1.json").write_text(
        json.dumps(report.metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    import pandas as pd

    pd.DataFrame({"actual": report.weekly_actual, "pred": report.weekly_pred}).to_csv(
        reports / "weekly_actual_vs_pred_v1.csv"
    )

    md = render_markdown(split_meta, dof, policy.train_metrics, report.metrics, prune_info)
    (reports / "run_v1.md").write_text(md, encoding="utf-8")
    print(md)
    print("\nГотово → reports/run_v1.md")


def render_markdown(split_meta, dof, train_m, metrics, prune_info) -> str:
    roles_lines = []
    for role, info in dof["roles"].items():
        roles_lines.append(
            f"- **{role}**: автоматов={info['n_automata']}, "
            f"действий={info['n_actions']}, "
            f"H≤{info['shannon_upper_bits']:.2f} бит"
        )
    return f"""# Прогон v1 — softmax-организм (BPIC2012)

## Философия
Компания = организм. Порядок эмерджентен из локальных мутаций **Information** через **Action**.
Политика агента — классический softmax (мультиномиальная логистика), не таблица частот.

## Донор
- BPI Challenge 2012 (один институт)
- Fit/holdout: {split_meta['fit_months']}м / {split_meta['holdout_months']}м
- Fit: {split_meta['fit_cases']} кейсов / {split_meta['fit_events']} событий
- Holdout: {split_meta['hold_cases']} кейсов / {split_meta['hold_events']} событий

## Обучение политики
- Модель: One-Hot(prev_activity, amount_bin, agent) → softmax(Action)
- Loss (аудит): L ≈ E[fail] + λH → CE + λ·entropy
- Fit accuracy: **{train_m['fit_action_accuracy']:.3f}**
- Fit CE: {train_m['cross_entropy']:.3f}, F≈{train_m['free_energy_proxy']:.3f}
- Прунинг редких Action: {json.dumps(prune_info.get('pruned_actions_by_role', {}), ensure_ascii=False)}

## Организм
- Нейроавтоматы: **{dof['n_automata']}** (1 resource = 1 агент)
- Information atoms: {dof['n_information_atoms']}, Action catalog: {dof['n_actions_catalog']}
{chr(10).join(roles_lines)}

## Holdout
```json
{json.dumps(metrics, ensure_ascii=False, indent=2)}
```

## Проверка на подлог
- Не «средний BPMN»: агент в признаках (individual softmax), мембрана роли маскирует Action.
- Не склейка корпусов: один донор.
- Эмпирика счётчиков заменена обучаемой P(Action|Information, agent).
"""


if __name__ == "__main__":
    main()
