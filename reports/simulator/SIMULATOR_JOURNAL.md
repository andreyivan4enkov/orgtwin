

---

## v0.9.0 — run_experiment (2026-09-03T14:38:16.493506+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/simulator/v0.9.0.json`
- Рецепт: softmax_fep_ab

### Holdout
- winner_next=softmax; winner_weekly=fep_habit_only
- comparison={"next_step_accuracy": {"softmax": 0.9368606138107417, "fep_habit_only": 0.9355019181585678, "fep_full_efe": 0.9349224744245525}, "top3_accuracy": {"softmax": 0.986233216112532, "fep_habit_only": 0.9865129475703325, "fep_full_efe": 0.98909047314578}, "weekly_events_corr": {"softmax": 0.9662901205314159, "fep_habit_only": 0.9795073515594247, "fep_full_efe": 0.9716190577960705}, "cross_entropy": {"softmax": 0.42621737483524524, "fep_habit_only": 0.31668880984960185, "fep_full_efe": 0.29186538708784887}, "sim_wall_sec": {"softmax": 9.719225548004033, "fep_habit_only": 11.963344589996268, "fep_full_efe": 12.503430662000028}}

### Решения
- BPIC2019: ingest обобщён (amount/roles/filters/subsample)
- Subsample для сопоставимого wall-time
- Timing — Ridge sidecar, не приоритет
- Контур=simulator; scripts/run_simulator.py (версия 0.9.0)
- package_version=0.10.0
- Фильтр донора: {'time_from': '2018-01-01 00:00:00+00:00', 'cases_after_time_filter': 251470, 'events_after_time_filter': 1587925}
- Subsample кейсов: {'seed': 42, 'fit_cases_sampled': 12000, 'hold_cases_sampled': 8000, 'fit_cases': 12000, 'hold_cases': 8000, 'fit_events': 78556, 'hold_events': 50293}
- FEP habit selected: {'mode': 'habit_only', 'gamma': 1.0, 'risk_w': 0.0, 'amb_w': 0.0, 'habit_w': 1.0, 'fit_acc': 0.951}
- FEP full selected: {'mode': 'full_efe', 'gamma': 2.0, 'risk_w': 0.25, 'amb_w': 0.25, 'habit_w': 1.0, 'fit_acc': 0.949}
- Победитель next-step: softmax
- Победитель weekly_corr: fep_habit_only

### Артефакты
- `reports/run_v0.9.0.md`, `run_v0.9.0_full.json`
