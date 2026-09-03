# OrgTwin v0.6.0

## Суть (RU)
Исправление FEP до паритета с softmax по контексту агента + тюнинг на fit.
Руки: softmax | fep_habit_only | fep_full_efe; кривой FEP 0.5.0 — из артефакта.

## 说明 (中文)
修正 FEP：智能体级 habit + 仅在 fit 上调参。对比 softmax / habit_only / full_efe；0.5.0 扭曲 FEP 来自既有产物。

## Holdout (raw)
| Метрика | Softmax | FEP habit | FEP full EFE | FEP 0.5.0 (кривой) |
|---------|---------|-----------|--------------|---------------------|
| next-step | 0.5504 | 0.5508 | 0.5484 | 0.4660 |
| top-3 | 0.9112 | 0.9019 | 0.9056 | 0.8465 |
| weekly_corr | 0.9216 | 0.8611 | 0.8610 | 0.8676 |

Δ habit−softmax next: +0.0004  
Δ full−softmax next: -0.0020  
Δ habit−0.5.0 next: +0.0848

Победитель next-step: **fep_habit_only**; weekly: **softmax**.

## Решения
- Релиз OrgTwin 0.6.0: FEP с agent-level habit + тюнинг на fit vs Softmax
- Holdout не используется для выбора гиперпараметров FEP
- 0.5.0 FEP (role-level) сохранён в reports/run_v0.5.0.* как кривой baseline
- Softmax: откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- FEP habit selected: {'mode': 'habit_only', 'gamma': 1.0, 'risk_w': 0.0, 'amb_w': 0.0, 'habit_w': 1.0, 'fit_acc': 0.57524}
- FEP full selected: {'mode': 'full_efe', 'gamma': 2.0, 'risk_w': 0.25, 'amb_w': 0.25, 'habit_w': 1.0, 'fit_acc': 0.5742}
- В отчёт включены метрики FEP 0.5.0 (role-level) из артефакта
- Победитель next-step: fep_habit_only
- Победитель weekly_corr: softmax
- FEP habit_only близок к softmax по next-step (Δ=+0.0004)

## Неудачи / риски
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
