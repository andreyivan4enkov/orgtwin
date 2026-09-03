"""
Декомпозиция следа на Information + Action → DoF → локальные правила.

Правило: степень свободы агента = только то, что он реально читал/писал в fit-окне.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import pandas as pd

from orgtwin.ingest.xes_loader import infer_role
from orgtwin.ir.basis import (
    Action,
    InformationAtom,
    LocalRule,
    Membrane,
    NeuroAutomaton,
    OrgGraph,
)


# Поля кейса/события, которые считаем Information (не метаданные парсера)
INFO_CANDIDATES = (
    "concept:name",
    "lifecycle:transition",
    "org:resource",
    "AMOUNT_REQ",
    "case:AMOUNT_REQ",
    "case:REG_DATE",
    "case:concept:name",
)


def _dtype_of(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "binary"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"
    nunique = series.dropna().nunique()
    if nunique <= 2:
        return "binary"
    if nunique <= 64:
        return "categorical"
    return "opaque"


def build_information_schema(df: pd.DataFrame) -> dict[str, InformationAtom]:
    schema: dict[str, InformationAtom] = {}
    for key in INFO_CANDIDATES:
        if key not in df.columns:
            continue
        s = df[key]
        dtype = _dtype_of(s)
        domain: tuple[Any, ...] = ()
        if dtype in {"categorical", "binary"}:
            vals = tuple(sorted(map(str, s.dropna().unique().tolist()))[:128])
            domain = vals
        # activity/lifecycle — записываются действиями; amount обычно кейс-атрибут (чтение)
        writable = key in {"concept:name", "lifecycle:transition"}
        schema[key] = InformationAtom(
            key=key,
            dtype=dtype,
            domain=domain,
            writable=writable,
            readable=True,
        )
    return schema


def build_actions_catalog(df: pd.DataFrame) -> dict[str, Action]:
    catalog: dict[str, Action] = {}
    cols = ["concept:name"]
    if "lifecycle:transition" in df.columns:
        cols.append("lifecycle:transition")
    grouped = df.groupby(cols, dropna=False).size().reset_index(name="n")
    for _, row in grouped.iterrows():
        act = str(row["concept:name"])
        life = row.get("lifecycle:transition")
        life_s = None if pd.isna(life) else str(life)
        name = act if life_s is None else f"{act}|{life_s}"
        # мутация: действие пишет имя активности (+ lifecycle) в след
        writes = ("concept:name",) if life_s is None else ("concept:name", "lifecycle:transition")
        # предусловие минимально: наличие кейса (case id) — всегда
        catalog[name] = Action(
            name=name,
            preconditions=("case:concept:name",),
            writes=writes,
            bits=1,
            lifecycle=life_s,
        )
    return catalog


def _condition_signature(row: pd.Series, keys: list[str]) -> str:
    parts = []
    for k in keys:
        if k not in row.index or pd.isna(row[k]):
            parts.append(f"{k}=∅")
        else:
            parts.append(f"{k}={row[k]}")
    return "|".join(parts)


def decompose_org(
    df: pd.DataFrame,
    donor_id: str = "BPIC2012",
    min_agent_events: int = 20,
) -> OrgGraph:
    schema = build_information_schema(df)
    actions = build_actions_catalog(df)

    # роль агента = доминирующий префикс активностей
    agent_role_votes: dict[str, Counter] = defaultdict(Counter)
    for _, row in df[["org:resource", "concept:name"]].iterrows():
        agent_role_votes[str(row["org:resource"])][infer_role(str(row["concept:name"]))] += 1

    agent_role = {
        a: votes.most_common(1)[0][0] if votes else "UNKNOWN"
        for a, votes in agent_role_votes.items()
    }

    # мембрана роли: объединение действий и сенсоров по всем агентам роли
    role_actions: dict[str, set[str]] = defaultdict(set)
    role_sensors: dict[str, set[str]] = defaultdict(set)
    for _, row in df.iterrows():
        agent = str(row["org:resource"])
        role = agent_role[agent]
        life = row.get("lifecycle:transition")
        act_name = (
            str(row["concept:name"])
            if pd.isna(life)
            else f"{row['concept:name']}|{life}"
        )
        role_actions[role].add(act_name)
        for key, atom in schema.items():
            if atom.readable and key in row.index and not pd.isna(row[key]):
                role_sensors[role].add(key)

    membranes: dict[str, Membrane] = {}
    for role, acts in role_actions.items():
        sensors = tuple(schema[k] for k in sorted(role_sensors[role]) if k in schema)
        act_objs = tuple(actions[a] for a in sorted(acts) if a in actions)
        membranes[role] = Membrane(role_id=role, sensors=sensors, actions=act_objs)

    # локальные правила: P(action | предыдущая активность кейса) — DoF из следа
    # предыдущая activity в кейсе = наблюдаемая Information перед мутацией
    df = df.copy()
    df["prev_activity"] = df.groupby("case:concept:name")["concept:name"].shift(1)
    cond_keys = ["prev_activity"]
    if "AMOUNT_REQ" in df.columns:
        # бининг суммы — грубая сенсорная проекция
        df["amount_bin"] = pd.qcut(df["AMOUNT_REQ"].rank(method="first"), q=4, labels=False, duplicates="drop")
        cond_keys.append("amount_bin")
    elif "case:AMOUNT_REQ" in df.columns:
        df["amount_bin"] = pd.qcut(
            df["case:AMOUNT_REQ"].rank(method="first"), q=4, labels=False, duplicates="drop"
        )
        cond_keys.append("amount_bin")

    agent_counts: dict[str, Counter] = defaultdict(Counter)
    agent_joint: dict[str, Counter] = defaultdict(Counter)
    agent_latency: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    prev_time: dict[str, pd.Timestamp] = {}
    for _, row in df.iterrows():
        agent = str(row["org:resource"])
        life = row.get("lifecycle:transition")
        act_name = (
            str(row["concept:name"])
            if pd.isna(life)
            else f"{row['concept:name']}|{life}"
        )
        sig = _condition_signature(row, cond_keys)
        agent_counts[agent][act_name] += 1
        agent_joint[agent][(sig, act_name)] += 1
        case = row["case:concept:name"]
        ts = row["time:timestamp"]
        if case in prev_time:
            dt = (ts - prev_time[case]).total_seconds()
            if 0 <= dt < 60 * 60 * 24 * 30:
                agent_latency[agent][act_name].append(dt)
        prev_time[case] = ts

    # hand-over: смена resource внутри кейса
    handovers: Counter = Counter()
    for case, g in df.groupby("case:concept:name"):
        resources = g["org:resource"].astype(str).tolist()
        for a, b in zip(resources, resources[1:]):
            if a != b:
                handovers[(a, b)] += 1

    automata: dict[str, NeuroAutomaton] = {}
    for agent, role in agent_role.items():
        n_events = int(sum(agent_counts[agent].values()))
        if n_events < min_agent_events and agent not in {"UNKNOWN", "nan"}:
            # всё равно создаём автомат, но помечаем малым следом
            pass
        membrane = membranes[role]
        # нормализация совместных счётчиков → LocalRule
        joint = agent_joint[agent]
        # знаменатели по сигнатуре
        denom: Counter = Counter()
        for (sig, _act), c in joint.items():
            denom[sig] += c
        rules: list[LocalRule] = []
        for (sig, act_name), c in joint.items():
            rules.append(
                LocalRule(
                    agent_id=agent,
                    role_id=role,
                    action_name=act_name,
                    condition_keys=tuple(cond_keys),
                    condition_signature=sig,
                    count=int(c),
                    probability=float(c) / float(denom[sig]),
                )
            )
        latency = {
            a: float(sum(v) / len(v)) for a, v in agent_latency[agent].items() if v
        }
        automata[agent] = NeuroAutomaton(
            agent_id=agent,
            role_id=role,
            membrane=membrane,
            rules=rules,
            action_latency_sec=latency,
            event_count=n_events,
        )

    return OrgGraph(
        donor_id=donor_id,
        automata=automata,
        handovers=dict(handovers),
        information_schema=schema,
        actions_catalog=actions,
    )


def degrees_of_freedom_report(graph: OrgGraph) -> dict:
    """Сводка DoF: информация + действия по ролям и агентам."""
    roles = sorted({a.role_id for a in graph.automata.values()})
    by_role = {}
    for role in roles:
        agents = [a for a in graph.automata.values() if a.role_id == role]
        m = agents[0].membrane if agents else None
        by_role[role] = {
            "n_automata": len(agents),
            "sensor_keys": [s.key for s in m.sensors] if m else [],
            "n_actions": len(m.actions) if m else 0,
            "action_names": [a.name for a in m.actions] if m else [],
            "bits_budget_max_action": m.bits_budget if m else 0,
            "shannon_upper_bits": m.shannon_upper_bits if m else 0.0,
            "total_events": int(sum(a.event_count for a in agents)),
        }
    return {
        "donor_id": graph.donor_id,
        "n_automata": len(graph.automata),
        "n_information_atoms": len(graph.information_schema),
        "n_actions_catalog": len(graph.actions_catalog),
        "n_handover_edges": len(graph.handovers),
        "roles": by_role,
    }
