"""
Базис IR: Information + Action.

- Information — поле/атом состояния в событийном следе
- Action — допустимая мутация Information при предусловиях
- Membrane роли = сенсоры + допустимые Action
- 1 org:resource = 1 NeuroAutomaton
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class InformationAtom:
    """Атомарная единица информации, наблюдаемая или записываемая в следе."""

    key: str
    dtype: str  # categorical | numeric | timestamp | binary | opaque
    domain: tuple[Any, ...] = ()  # дискретные значения, если известны
    writable: bool = False  # может ли агент мутировать это поле действием
    readable: bool = True  # входит ли в сенсорную проекцию мембраны


@dataclass(frozen=True)
class Action:
    """Мутация информации: предусловие → изменение полей Information."""

    name: str
    preconditions: tuple[str, ...]  # ключи Information / предикаты, нужные до действия
    writes: tuple[str, ...]  # какие InformationAtom мутируются
    bits: int = 1  # верхняя оценка log2(|допустимых Action|) на мембране роли
    lifecycle: Optional[str] = None  # start|complete|schedule|...


@dataclass
class Membrane:
    """Мембрана роли: сенсоры (Information) + допустимые Action."""

    role_id: str
    sensors: tuple[InformationAtom, ...]
    actions: tuple[Action, ...]

    @property
    def bits_budget(self) -> int:
        return max((a.bits for a in self.actions), default=0)

    @property
    def shannon_upper_bits(self) -> float:
        # верхняя оценка энтропии выбора: log2(|A|) при равномерности
        n = len(self.actions)
        if n <= 1:
            return 0.0
        import math

        return math.log2(n)


@dataclass
class LocalRule:
    """
    Устаревший след v0 (счётчики). В v1 политика = SoftmaxPolicyBundle.
    Оставляем тип для совместимости отчётов.
    """

    agent_id: str
    role_id: str
    action_name: str
    condition_keys: tuple[str, ...]
    condition_signature: str
    count: int
    probability: float


@dataclass
class NeuroAutomaton:
    """Один сотрудник = один экземпляр. Политика — внешний softmax по Information."""

    agent_id: str
    role_id: str
    membrane: Membrane
    rules: list[LocalRule] = field(default_factory=list)
    action_latency_sec: dict[str, float] = field(default_factory=dict)
    event_count: int = 0


@dataclass
class OrgGraph:
    """Плоский граф: узлы = нейроавтоматы, рёбра = hand-over Information/Action."""

    donor_id: str
    automata: dict[str, NeuroAutomaton]
    # hand-over: (from_agent, to_agent) -> count
    handovers: dict[tuple[str, str], int] = field(default_factory=dict)
    information_schema: dict[str, InformationAtom] = field(default_factory=dict)
    actions_catalog: dict[str, Action] = field(default_factory=dict)
