# OrgTwin v0.7.0

## Русский
0.7.0: единый run_experiment.py; гиперпараметры и руки — только из этого JSON. Рецепт метрик тот же, что 0.6.0 (softmax_fep_ab).

Рецепт: `softmax_fep_ab`. Конфиг: `configs/experiments/v0.7.0.json`.

## 中文
0.7.0：统一 run_experiment.py；差异仅在本 JSON。评测配方与 0.6.0 相同（softmax_fep_ab）。

## Holdout (raw)
| Метрика | softmax | fep_habit_only | fep_full_efe |
|---------|------|------|------|
| next-step | 0.5504 | 0.5508 | 0.5484 |
| top-3 | 0.9112 | 0.9019 | 0.9056 |
| weekly_corr | 0.9216 | 0.8611 | 0.8610 |

Победитель next-step: **fep_habit_only**; weekly: **softmax**.

## Решения
- Антипаттерн копий run_v*.py закрыт: один entrypoint + configs/experiments/
- TECH_DEBT.md: timing отдельно, Python-циклы FEP, один донор BPIC2012
- Прогон через scripts/run_experiment.py --config (версия 0.7.0)
- package_version=0.7.0
- Softmax: откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- FEP habit selected: {'mode': 'habit_only', 'gamma': 1.0, 'risk_w': 0.0, 'amb_w': 0.0, 'habit_w': 1.0, 'fit_acc': 0.57524}
- FEP full selected: {'mode': 'full_efe', 'gamma': 2.0, 'risk_w': 0.25, 'amb_w': 0.25, 'habit_w': 1.0, 'fit_acc': 0.5742}
- Сравнение с артефактом: reports/holdout_metrics_v0.5.0.json
- Победитель next-step: fep_habit_only
- Победитель weekly_corr: softmax

## Неудачи / риски
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
