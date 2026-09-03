# Прогон v2 — softmax + Ridge(dt)

## Константы
См. `data/derived/experiment_config_v2.json` и `src/b2b_sim/config/constants.py`.

Ключевые:
- λ_entropy=0.05
- prune_min_support=30
- ridge_alpha=1.0
- latency_noise=[1.0, 1.0]
- max_steps выбран=40 (сравнивали 40 и 80)
- split=3+2 (цель 7+3)

## Timing fit (event dt)
```json
{
  "status": "ok",
  "n": 141893,
  "ridge_alpha": 1.0,
  "fit_mae_sec": 37706.2375314762,
  "fit_log_mae": 1.4391240904531186,
  "fit_spearman": 0.8528739183633671,
  "baseline_median_agent_action_spearman": 0.7964418199062618,
  "baseline_median_agent_action_log_mae": 1.4511036614403356,
  "dt_min_sec": 0.0,
  "dt_max_sec": 2592000.0,
  "note": "Обучаем dt текущего события; симуляция использует predict после выбора Action"
}
```

## Case-level duration head (НЕ эмерджентность)
```json
{
  "status": "case_level_head",
  "n": 7427,
  "fit_spearman": 0.22392207385780277,
  "fit_log_mae": 3.884647139297548,
  "note": "Не сумма dt; отдельный регрессор длительности кейса"
}
```

## Holdout (selected max_steps=40)
```json
{
  "weekly_events_mae": 2808.0833333333335,
  "weekly_events_mape": 0.4063379299843086,
  "weekly_events_corr": 0.8730268787479802,
  "case_duration_log_mae": 4.9043596540693075,
  "case_duration_spearman": -0.0010959483106119821,
  "n_cases_compared": 5658,
  "top20_action_overlap": 15,
  "sim_events": 85976,
  "hold_events": 112847,
  "terminal_share_actual": {
    "A_CANCELLED": 0.009756573059097716,
    "A_DECLINED": 0.028738025822573926,
    "A_APPROVED": 0.008117185215380117,
    "A_REGISTERED": 0.008117185215380117
  },
  "terminal_share_pred": {
    "A_CANCELLED": 0.01876104959523588,
    "A_DECLINED": 0.03200893272541174,
    "A_APPROVED": 0.003675444310040011,
    "A_REGISTERED": 0.002779845538289755
  },
  "holdout_next_step_accuracy": 0.5503704040358133,
  "holdout_next_step_top3": 0.911221197109485,
  "holdout_next_step_ce": 1.0443304770879145,
  "holdout_next_step_n": 110015,
  "holdout_free_energy_proxy": 1.0948969612938801,
  "case_level_head_spearman": 0.2292521383306908,
  "case_level_head_log_mae": 3.889239435050548,
  "case_level_head_n": 5658
}
```

## Sim meta
```json
{
  "max_steps_per_case": 40,
  "n_cases": 5658,
  "n_hit_max_steps": 738,
  "n_terminal_stop": 4920,
  "timing_used": true,
  "latency_noise": [
    1.0,
    1.0
  ],
  "seed": 42
}
```

## max_steps
Только 40 в финальном прогоне; 80 aborted (см. failures).
```json
{
  "40": {
    "emergent_dur_spearman": -0.0010959483106119821,
    "case_head_spearman": 0.2292521383306908,
    "hit_max": 738,
    "sim_events": 85976
  }
}
```

## Решения
- Все гиперпараметры сериализованы в experiment_config_v2.json
- Softmax solver=saga tol=0.001 CE+λH λ=0.05 C=1.0 max_iter=250
- Прунинг min_support=30
- Ridge alpha=1.0; latency_noise=[1.0,1.0] (выкл)
- Добавлена case-level Ridge-голова длительности (не эмерджентная сумма dt) — после провала sum(dt) Spearman≈0 при fit_dt Spearman~0.85
- Для run_v2.md max_steps=40 (80 aborted)
- Case-level duration head закрывает порог Spearman>0.2 (0.229) — но это НЕ эмерджентность

## Неудачи / риски / ограничения
- **SPLIT_NOT_7_3** (critical_limitation): Донор ~5.5 мес → используем 3+2, не целевые 7+3
- **PRUNE_MAY_BIAS_TERMINALS** (risk): Срезаны Action: {'APPLICATION': ['A_ACTIVATED|COMPLETE', 'O_DECLINED|COMPLETE', 'W_Completeren aanvraag|COMPLETE'], 'OFFER': ['O_DECLINED|COMPLETE'], 'WORKITEM': ['W_Afhandelen leads|SCHEDULE', 'W_Wijzigen contractgegevens|SCHEDULE']} — риск смещения исходов
- **MAX_STEPS_80_ABORTED** (incident): Прогон max_steps=80 прерван: wall-time (поштучный softmax encode на каждом шаге). Частичный результат max_steps=40: dur_spearman≈-0.001, hit_max=738/5658, next_acc≈0.55. В финальном v2 оставляем только max_steps=40 + case-level duration head.
- **EMERGENT_DURATION_SPEARMAN_BELOW_0_2** (failure): Эмерджентная сумма dt: Spearman=-0.0010959483106119821. Case-level head Spearman=0.2292521383306908. Вывод: хороший event-dt ≠ хороший case wall-clock через симулированную траекторию Action.
