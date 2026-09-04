"""
Единый реестр констант и гиперпараметров.

Любое изменение константы фиксировать в reports/LAB_JOURNAL.md
с причиной, старым значением и результатом прогона.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SplitConfig:
    """BPIC2012 покрывает ~5.5 мес → 3+2 как пропорция к целевым 7+3."""

    fit_months: int = 3
    holdout_months: int = 2
    # целевой протокол (когда будет год данных)
    target_fit_months: int = 7
    target_holdout_months: int = 3


@dataclass(frozen=True)
class PolicyConfig:
    lambda_entropy: float = 0.05  # λ в L ≈ CE + λ H (аудит / FEP-прокси)
    max_iter: int = 250
    C: float = 1.0
    random_state: int = 42
    # v1: lbfgs; v2: saga (быстрее на широком one-hot; tol=1e-3)
    solver: str = "saga"
    tol: float = 1e-3
    amount_quantiles: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)
    prune_min_support: int = 30
    terminal_prefixes: tuple[str, ...] = (
        "A_CANCELLED",
        "A_DECLINED",
        "A_APPROVED",
        "A_REGISTERED",
    )


@dataclass(frozen=True)
class TimingConfig:
    """Модель задержек между событиями (v2)."""

    # отбрасываем dt вне окна как выбросы при обучении
    dt_min_sec: float = 0.0
    dt_max_sec: float = 60.0 * 60 * 24 * 30  # 30 суток — было жёстко в v0/v1
    # fallback если нет прогноза
    default_latency_sec: float = 3600.0
    # v1 использовал U(0.7, 1.3) — УБРАНО в v2 (ломало Spearman)
    latency_noise_low: float = 1.0
    latency_noise_high: float = 1.0
    # Ridge на log1p(dt)
    ridge_alpha: float = 1.0
    min_train_dt_samples: int = 100
    # ускорение: subsample для Ridge (полный fit ~100k+ строк ок; для softmax — отдельно)
    # НЕ subsample softmax без записи в журнал


@dataclass(frozen=True)
class SimConfig:
    max_steps_per_case: int = 40  # обрезает длинные кейсы в legacy batch-режиме
    seed: int = 42
    # --- честный DES (queue_des) ---
    queue_mode: bool = False
    agent_capacity: int = 1
    input_flow_multiplier: float = 1.0
    max_sim_horizon_sec: float | None = None  # обрезка горизонта (сек сим-времени)


@dataclass(frozen=True)
class EvalConfig:
    top_k_actions: int = 20
    next_step_top_k: int = 3


@dataclass(frozen=True)
class FEPPolicyConfig:
    """Ожидаемая свободная энергия (Friston); см. policy/fep.py."""

    dirichlet_alpha: float = 0.5
    gamma_precision: float = 4.0
    preference_power: float = 1.0
    habit_weight: float = 1.0
    ambiguity_weight: float = 0.0
    risk_weight: float = 0.0
    empty_transition_entropy: float = 3.0
    mode: str = "habit_only"
    tune_on_fit: bool = True
    tune_eval_max_rows: int = 25000


@dataclass(frozen=True)
class DonorAdaptConfig:
    """Как читать агента и видимую информацию с конкретного лога."""

    agent_column: str = "org:resource"
    context_column: str = ""  # пусто = авто (AMOUNT_REQ / Age)
    role_mode: str = "activity_prefix"  # activity_prefix | agent | specialism
    count_min_support: int = 3
    compare_softmax: bool = True
    run_sim: bool = False
    min_input_support: int = 20
    min_unique_action_support: int = 30
    unique_share: float = 0.8
    top1_stuck_threshold: float = 0.8


@dataclass(frozen=True)
class ExperimentConfig:
    donor_id: str = "BPIC2012"
    donor_doi: str = "10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f"
    split: SplitConfig = SplitConfig()
    policy: PolicyConfig = PolicyConfig()
    fep: FEPPolicyConfig = FEPPolicyConfig()
    timing: TimingConfig = TimingConfig()
    sim: SimConfig = SimConfig()
    eval: EvalConfig = EvalConfig()
    donor_adapt: DonorAdaptConfig = DonorAdaptConfig()

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = ExperimentConfig()
