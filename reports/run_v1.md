# Прогон v1 — softmax (BPIC2012)

## Суть
Локальные политики P(Action|Information, agent); симуляция holdout.

## Донор
- BPI Challenge 2012 (один институт)
- Fit/holdout: 3м / 2м
- Fit: 7427 кейсов / 149330 событий
- Holdout: 5658 кейсов / 112847 событий

## Обучение политики
- Модель: One-Hot(prev_activity, amount_bin, agent) → softmax(Action)
- Loss-прокси: L ≈ E[fail] + λH → CE + λ·entropy
- Fit accuracy: **0.563**
- Fit CE: 0.978, F≈1.028
- Прунинг редких Action: {"APPLICATION": ["A_ACTIVATED|COMPLETE", "O_DECLINED|COMPLETE", "W_Completeren aanvraag|COMPLETE"], "OFFER": ["O_DECLINED|COMPLETE"], "WORKITEM": ["W_Afhandelen leads|SCHEDULE", "W_Wijzigen contractgegevens|SCHEDULE"]}

## Организм
- Нейроавтоматы: **65** (1 resource = 1 агент)
- Information atoms: 8, Action catalog: 36
- **APPLICATION**: автоматов=4, действий=16, H≤4.00 бит
- **OFFER**: автоматов=6, действий=10, H≤3.32 бит
- **WORKITEM**: автоматов=55, действий=32, H≤5.00 бит

## Holdout
```json
{
  "weekly_events_mae": 2219.785714285714,
  "weekly_events_mape": 4.9681359749780745,
  "weekly_events_corr": 0.9548597973344464,
  "case_duration_log_mae": 4.1844975614734565,
  "case_duration_spearman": 0.004095026680042873,
  "n_cases_compared": 5658,
  "top20_action_overlap": 15,
  "sim_events": 84006,
  "hold_events": 112847,
  "terminal_share_actual": {
    "A_CANCELLED": 0.009756573059097716,
    "A_DECLINED": 0.028738025822573926,
    "A_APPROVED": 0.008117185215380117,
    "A_REGISTERED": 0.008117185215380117
  },
  "terminal_share_pred": {
    "A_CANCELLED": 0.018593909958812466,
    "A_DECLINED": 0.033521415137014024,
    "A_APPROVED": 0.003452134371354427,
    "A_REGISTERED": 0.0027021879389567413
  },
  "holdout_next_step_accuracy": 0.5507612598282052,
  "holdout_next_step_top3": 0.9114302595100668,
  "holdout_next_step_ce": 1.0443884925417437,
  "holdout_next_step_n": 110015,
  "holdout_free_energy_proxy": 1.094936743328744
}
```

## Проверка на подлог
- Не «средний BPMN»: агент в признаках (individual softmax), мембрана роли маскирует Action.
- Не склейка корпусов: один донор.
- Эмпирика счётчиков заменена обучаемой P(Action|Information, agent).
