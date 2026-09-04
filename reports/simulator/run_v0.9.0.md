# OrgTwin v0.9.0

## Русский
0.9.0: третий организм BPIC2019 (закупки NL). Фильтр с 2018-01-01; subsample 12k+8k; amount=Cumulative net worth (EUR); роли procurement.

Рецепт: `softmax_fep_ab`. Конфиг: `configs/simulator/v0.9.0.json`.

## 中文
0.9.0：第三数据源 BPIC2019（荷兰采购）。自 2018-01-01 过滤；子采样 12k+8k；金额=Cumulative net worth (EUR)；角色 procurement。

## Holdout (raw)
| Метрика | softmax | fep_habit_only | fep_full_efe |
|---------|------|------|------|
| next-step | 0.9369 | 0.9355 | 0.9349 |
| top-3 | 0.9862 | 0.9865 | 0.9891 |
| weekly_corr | 0.9663 | 0.9795 | 0.9716 |

Победитель next-step: **softmax**; weekly: **fep_habit_only**.

## Решения
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

## Неудачи / риски
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
