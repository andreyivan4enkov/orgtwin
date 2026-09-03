"""
Модель времени: классический Ridge на log1p(dt).

Information+Action+agent → задержка до следующего события.
Фиксирует провал v1 (Spearman≈0): убираем U(0.7,1.3), учитываем prev/action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

from orgtwin.config.constants import TimingConfig, DEFAULT
from orgtwin.policy.softmax import prepare_trace_frame


@dataclass
class TimingModel:
    encoder: OneHotEncoder
    model: Ridge
    feature_cols: list[str]
    train_metrics: dict = field(default_factory=dict)
    cfg: TimingConfig = field(default_factory=lambda: DEFAULT.timing)

    def predict_dt_sec(
        self,
        prev_activity: Any,
        action: str,
        agent: str,
        amount_bin: Any,
    ) -> float:
        row = pd.DataFrame(
            [
                {
                    "prev_activity": str(prev_activity if prev_activity is not None else "∅"),
                    "action": str(action),
                    "agent": str(agent),
                    "amount_bin": str(amount_bin if amount_bin is not None else "0"),
                }
            ]
        )
        X = self.encoder.transform(row[self.feature_cols].astype(str))
        log_dt = float(self.model.predict(X)[0])
        dt = float(np.expm1(log_dt))
        dt = max(self.cfg.dt_min_sec + 1e-3, min(dt, self.cfg.dt_max_sec))
        return dt


def train_timing_model(
    fit_df: pd.DataFrame,
    policy: Any,
    cfg: TimingConfig | None = None,
) -> TimingModel:
    cfg = cfg or DEFAULT.timing
    framed, _ = prepare_trace_frame(fit_df, amount_bin_edges=policy.amount_bin_edges)
    framed = framed.sort_values(["case:concept:name", "time:timestamp"]).copy()
    framed["dt"] = (
        framed.groupby("case:concept:name")["time:timestamp"].diff().dt.total_seconds()
    )
    # dt относится к интервалу ПЕРЕД текущим событием; для обучения
    # предсказываем dt текущего шага по (prev, action, agent) текущего события
    use = framed.dropna(subset=["dt"]).copy()
    use = use[(use["dt"] >= cfg.dt_min_sec) & (use["dt"] < cfg.dt_max_sec)]

    feature_cols = ["prev_activity", "action", "agent", "amount_bin"]
    if len(use) < cfg.min_train_dt_samples:
        # деградация: константа
        median_dt = float(use["dt"].median()) if len(use) else cfg.default_latency_sec
        enc = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        # фиктивный fit
        X = enc.fit_transform(use[feature_cols].astype(str) if len(use) else pd.DataFrame(
            [{"prev_activity": "∅", "action": "A_SUBMITTED|COMPLETE", "agent": "UNKNOWN", "amount_bin": "0"}]
        ))
        model = Ridge(alpha=cfg.ridge_alpha)
        y = np.log1p(use["dt"].to_numpy()) if len(use) else np.array([np.log1p(median_dt)])
        if len(use):
            model.fit(X, y)
        else:
            model.fit(X, y)
        return TimingModel(
            encoder=enc,
            model=model,
            feature_cols=feature_cols,
            train_metrics={
                "status": "degraded_few_samples",
                "n": int(len(use)),
                "median_dt": median_dt,
            },
            cfg=cfg,
        )

    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    X = enc.fit_transform(use[feature_cols].astype(str))
    y = np.log1p(use["dt"].to_numpy(dtype=float))
    model = Ridge(alpha=cfg.ridge_alpha)
    model.fit(X, y)
    pred = np.expm1(model.predict(X))
    actual = use["dt"].to_numpy(dtype=float)
    # метрики fit
    mae = float(np.mean(np.abs(pred - actual)))
    log_mae = float(np.mean(np.abs(np.log1p(pred) - np.log1p(actual))))
    # spearman через pandas
    spearman = float(pd.Series(pred).corr(pd.Series(actual), method="spearman"))
    # сравнение с медианой (agent,action) — бейзлайн v1
    med = use.groupby(["agent", "action"])["dt"].transform("median")
    base_spearman = float(pd.Series(med.to_numpy()).corr(pd.Series(actual), method="spearman"))
    base_log_mae = float(np.mean(np.abs(np.log1p(med.to_numpy()) - np.log1p(actual))))

    metrics = {
        "status": "ok",
        "n": int(len(use)),
        "ridge_alpha": cfg.ridge_alpha,
        "fit_mae_sec": mae,
        "fit_log_mae": log_mae,
        "fit_spearman": spearman,
        "baseline_median_agent_action_spearman": base_spearman,
        "baseline_median_agent_action_log_mae": base_log_mae,
        "dt_min_sec": cfg.dt_min_sec,
        "dt_max_sec": cfg.dt_max_sec,
        "note": "Обучаем dt текущего события; симуляция использует predict после выбора Action",
    }
    return TimingModel(
        encoder=enc,
        model=model,
        feature_cols=feature_cols,
        train_metrics=metrics,
        cfg=cfg,
    )


def train_case_duration_model(
    fit_df: pd.DataFrame,
    policy: Any,
    cfg: TimingConfig | None = None,
) -> TimingModel:
    """
    Параллельная голова: log1p(case_duration) от стартовой Information.
    НЕ эмерджентная сумма dt — отдельный классический регрессор.
    Нужна: сумма симулированных dt даёт Spearman≈0 даже при fit_spearman(dt)~0.85.
    """
    cfg = cfg or DEFAULT.timing
    first = (
        fit_df.sort_values("time:timestamp")
        .groupby("case:concept:name", as_index=False)
        .first()
    )
    dur = fit_df.groupby("case:concept:name")["time:timestamp"].agg(
        lambda s: float((s.max() - s.min()).total_seconds())
    )
    dur.name = "duration"
    first = first.merge(dur, left_on="case:concept:name", right_index=True)
    framed, _ = prepare_trace_frame(first, amount_bin_edges=policy.amount_bin_edges)
    feature_cols = ["prev_activity", "action", "agent", "amount_bin"]
    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
    X = enc.fit_transform(framed[feature_cols].astype(str))
    y = np.log1p(np.clip(framed["duration"].to_numpy(dtype=float), 0, None))
    model = Ridge(alpha=cfg.ridge_alpha)
    model.fit(X, y)
    pred = np.expm1(model.predict(X))
    actual = framed["duration"].to_numpy(dtype=float)
    spearman = float(pd.Series(pred).corr(pd.Series(actual), method="spearman"))
    return TimingModel(
        encoder=enc,
        model=model,
        feature_cols=feature_cols,
        train_metrics={
            "status": "case_level_head",
            "n": int(len(framed)),
            "fit_spearman": spearman,
            "fit_log_mae": float(
                np.mean(np.abs(np.log1p(pred) - np.log1p(np.maximum(actual, 0))))
            ),
            "note": "Не сумма dt; отдельный регрессор длительности кейса",
        },
        cfg=cfg,
    )


def predict_case_durations(
    model: TimingModel,
    hold_df: pd.DataFrame,
    policy: Any,
) -> dict[str, float]:
    first = (
        hold_df.sort_values("time:timestamp")
        .groupby("case:concept:name", as_index=False)
        .first()
    )
    framed, _ = prepare_trace_frame(first, amount_bin_edges=policy.amount_bin_edges)
    X = model.encoder.transform(framed[model.feature_cols].astype(str))
    pred = np.expm1(model.model.predict(X))
    return {
        str(c): float(max(0.0, p))
        for c, p in zip(framed["case:concept:name"], pred)
    }
