"""Greenfield: синтетический поток из design без XES."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


TEMPLATES: dict[str, dict[str, Any]] = {
    "credit": {
        "label": "Шаблон: кредит",
        "roles": [
            {"id": "APPLICATION", "label": "Отдел заявок"},
            {"id": "OFFER", "label": "Отдел предложений"},
            {"id": "WORKITEM", "label": "Исполнение"},
        ],
        "agents": [
            {"id": "A1", "role_id": "APPLICATION", "capacity": 1},
            {"id": "A2", "role_id": "APPLICATION", "capacity": 1},
            {"id": "O1", "role_id": "OFFER", "capacity": 1},
            {"id": "W1", "role_id": "WORKITEM", "capacity": 1},
            {"id": "W2", "role_id": "WORKITEM", "capacity": 1},
        ],
        "edges": [
            {"from_agent": "A1", "to_agent": "O1", "weight": 0.6},
            {"from_agent": "A2", "to_agent": "O1", "weight": 0.5},
            {"from_agent": "O1", "to_agent": "W1", "weight": 0.5},
            {"from_agent": "O1", "to_agent": "W2", "weight": 0.4},
            {"from_agent": "W1", "to_agent": "W2", "weight": 0.3},
        ],
    },
    "procurement": {
        "label": "Шаблон: закупки",
        "roles": [
            {"id": "PR", "label": "Заявки"},
            {"id": "PO", "label": "Заказы"},
            {"id": "GR", "label": "Приёмка"},
            {"id": "INV", "label": "Счета"},
        ],
        "agents": [
            {"id": "PR1", "role_id": "PR", "capacity": 1},
            {"id": "PO1", "role_id": "PO", "capacity": 1},
            {"id": "GR1", "role_id": "GR", "capacity": 1},
            {"id": "INV1", "role_id": "INV", "capacity": 1},
        ],
        "edges": [
            {"from_agent": "PR1", "to_agent": "PO1", "weight": 0.7},
            {"from_agent": "PO1", "to_agent": "GR1", "weight": 0.6},
            {"from_agent": "GR1", "to_agent": "INV1", "weight": 0.5},
        ],
    },
    "clinic": {
        "label": "Шаблон: клиника",
        "roles": [
            {"id": "WARD", "label": "Палаты"},
            {"id": "LAB", "label": "Лаборатория"},
            {"id": "CLINIC", "label": "Клиника"},
        ],
        "agents": [
            {"id": "Nursing ward", "role_id": "WARD", "capacity": 2},
            {"id": "General Lab Clinical Chemistry", "role_id": "LAB", "capacity": 2},
            {"id": "Internal Specialisms clinic", "role_id": "CLINIC", "capacity": 1},
        ],
        "edges": [
            {"from_agent": "Nursing ward", "to_agent": "General Lab Clinical Chemistry", "weight": 0.55},
            {"from_agent": "General Lab Clinical Chemistry", "to_agent": "Nursing ward", "weight": 0.4},
            {"from_agent": "General Lab Clinical Chemistry", "to_agent": "Internal Specialisms clinic", "weight": 0.25},
        ],
    },
}


def synthesize_event_log(
    design: dict[str, Any],
    *,
    n_cases: int = 200,
    steps_per_case: int = 6,
    seed: int = 42,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """Синтетический лог из ролей/агентов/рёбер. Метка происхождения — assumption."""
    rng = np.random.default_rng(seed)
    agents = [str(a["id"]) for a in design.get("agents") or []]
    if not agents:
        agents = ["A1"]
    # переходная матрица по рёбрам
    succ: dict[str, list[tuple[str, float]]] = {a: [] for a in agents}
    for e in design.get("edges") or []:
        frm, to = str(e["from_agent"]), str(e["to_agent"])
        if frm in succ and to in agents:
            succ[frm].append((to, float(e.get("weight", 0.3))))
    for a in agents:
        if not succ[a]:
            succ[a] = [(b, 1.0 / len(agents)) for b in agents]

    rows = []
    t0 = pd.Timestamp(start, tz="UTC")
    for i in range(n_cases):
        cid = f"GF-{i:04d}"
        agent = str(rng.choice(agents))
        t = t0 + pd.Timedelta(days=float(rng.integers(0, 320)), hours=float(rng.integers(0, 24)))
        for step in range(steps_per_case):
            rows.append(
                {
                    "case:concept:name": cid,
                    "concept:name": f"STEP_{step}",
                    "lifecycle:transition": "COMPLETE",
                    "time:timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "org:resource": agent,
                    "origin": "assumption",
                }
            )
            opts = succ.get(agent) or [(a, 1.0) for a in agents]
            labels = [o[0] for o in opts]
            probs = np.array([o[1] for o in opts], dtype=float)
            probs = probs / probs.sum()
            agent = str(rng.choice(labels, p=probs))
            t = t + pd.Timedelta(hours=float(rng.uniform(0.5, 8.0)))
    return pd.DataFrame(rows)
