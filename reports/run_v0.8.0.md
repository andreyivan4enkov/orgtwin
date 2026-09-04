# OrgTwin v0.8.0

0.8.0: ядро = локальные правила P(действие|видимое,агент). Донор — Hospital log (BPIC2011), один NL academic hospital. Агент = org:group (отделение, не физлицо). Split 7+3 мес от начала лога. Softmax только A/B по CE. Без FEP, без калибровки длительности, без стресса top-3, без прунинга 30.

Рецепт: `agent_rules`. Конфиг: `configs/experiments/v0.8.0.json`.
Политика (по CE holdout): **softmax**.

## Holdout next-step
| Метрика | counts | softmax |
|---------|------|------|
| next-step | 0.6244 | 0.6295 |
| top-3 | 0.8499 | 0.8617 |
| CE | 2.2234 | 1.2965 |

## Локальные минимумы (fit)
Агентов: 33; с незаменимыми частыми действиями: 13.

- `Hyper Pressure Tank`: n=30, H≈0.0000, stuck_frac=1.0000, действий 1/3, уник. частых=1
- `ICU Adults`: n=65, H≈nan, stuck_frac=nan, действий 14/24, уник. частых=0
- `Pharmacy Laboratory`: n=117, H≈0.0000, stuck_frac=1.0000, действий 3/168, уник. частых=1
- `Internal Specialisms clinic`: n=755, H≈0.8120, stuck_frac=0.7819, действий 11/13, уник. частых=1
- `Lab Experimental Immunology`: n=1, H≈nan, stuck_frac=nan, действий 1/168, уник. частых=0
- `Lab Hematology`: n=2, H≈nan, stuck_frac=nan, действий 1/168, уник. частых=0
- `Medical Microbiology`: n=1166, H≈0.9537, stuck_frac=0.2326, действий 15/15, уник. частых=4
- `Anesthesiology`: n=1, H≈nan, stuck_frac=nan, действий 1/24, уник. частых=0

## Решения
- Срез обвязки: FEP / case-head / stress / prune вне критического пути
- Второй организм: HOSPITAL2011, не склеивать с BPIC2012
- Прогон recipe=agent_rules через run_experiment.py (версия 0.8.0)
- package_version=0.8.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.2965 < 2.2234) — политика = softmax
- Диагностика: агентов=33, незаменимых частых действий (уник. носитель)=61

## Ограничения
—
