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
    max_steps_per_case: int = 40  # ПОДОЗРЕНИЕ: обрезает длинные кейсы
    seed: int = 42
    # hand-over stay mass = sum(outgoing) — эвристика v1, не из данных напрямую
    # в softmax.py: stay = s; probs[a]=stay/(s+stay)


@dataclass(frozen=True)
class EvalConfig:
    top_k_actions: int = 20
    next_step_top_k: int = 3


@dataclass(frozen=True)
class ExperimentConfig:
    donor_id: str = "BPIC2012"
    donor_doi: str = "10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f"
    split: SplitConfig = SplitConfig()
    policy: PolicyConfig = PolicyConfig()
    timing: TimingConfig = TimingConfig()
    sim: SimConfig = SimConfig()
    eval: EvalConfig = EvalConfig()

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = ExperimentConfig()
