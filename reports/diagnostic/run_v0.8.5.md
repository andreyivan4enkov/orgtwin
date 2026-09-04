# OrgTwin v0.8.5

0.8.5: BPIC2012; directed edge semantics: какие Information-поля меняются перед hand-over (A→B).

Рецепт: `agent_rules`. Конфиг: `configs/diagnostic/v0.8.5.json`.
Политика (по CE holdout): **softmax**.

## Holdout next-step
| Метрика | counts | softmax |
|---------|------|------|
| next-step | 0.5457 | 0.5504 |
| top-3 | 0.8924 | 0.9112 |
| CE | 1.6623 | 1.0406 |

## Локальные минимумы (fit)
Агентов: 65; с незаменимыми частыми действиями: 2.

- `10609`: n=3952, H≈2.1201, stuck_frac=0.1224, действий 30/34, уник. частых=0
- `10228`: n=404, H≈1.7313, stuck_frac=0.0636, действий 20/34, уник. частых=0
- `10124`: n=4, H≈nan, stuck_frac=nan, действий 3/34, уник. частых=0
- `10125`: n=6, H≈nan, stuck_frac=nan, действий 3/34, уник. частых=0
- `10862`: n=451, H≈0.8076, stuck_frac=0.3879, действий 10/11, уник. частых=0
- `10880`: n=660, H≈0.8040, stuck_frac=0.3816, действий 9/11, уник. частых=0
- `10859`: n=338, H≈0.8128, stuck_frac=0.2824, действий 10/19, уник. частых=0
- `10910`: n=3369, H≈1.5645, stuck_frac=0.1935, действий 26/34, уник. частых=0

## Directed Edge Field (fit)
Агентов: 65; рёбер: 1694 / 4160; плотность: 0.4072.

- `112 → UNKNOWN`: n=1214, Pout=0.2184, Pin=0.1814, asym=0.1968, H_from=4.4705
- `112 → 11189`: n=449, Pout=0.0808, Pin=0.3046, asym=0.0737, H_from=4.4705
- `112 → 11169`: n=406, Pout=0.0730, Pin=0.3641, asym=0.0655, H_from=4.4705
- `112 → 10910`: n=377, Pout=0.0678, Pin=0.4724, asym=0.0610, H_from=4.4705
- `11029 → UNKNOWN`: n=368, Pout=1.0000, Pin=0.0550, asym=0.9398, H_from=0.0000
- `UNKNOWN → 11029`: n=368, Pout=0.0602, Pin=1.0000, asym=-0.9398, H_from=5.2832
- `11200 → UNKNOWN`: n=363, Pout=1.0000, Pin=0.0542, asym=0.9406, H_from=0.0000
- `UNKNOWN → 11200`: n=363, Pout=0.0594, Pin=1.0000, asym=-0.9406, H_from=5.2832

## Entity-Edge Layer (fit)
Сущностей: 110; рёбер: 3129.  
Типы сущностей: {'agent': 65, 'action': 36, 'information_field': 6, 'membrane': 3}.  
Типы рёбер: {'agent_to_action': 1178, 'membrane_to_action': 64, 'membrane_to_information_field': 18, 'action_to_action': 175, 'agent_to_agent': 1694}.

- `action_to_action`: топ `action:W_Nabellen offertes|COMPLETE → action:W_Nabellen offertes|START` (n=10651, p=0.8060)
- `agent_to_action`: топ `agent:112 → action:A_PARTLYSUBMITTED|COMPLETE` (n=7427, p=0.2849)
- `agent_to_agent`: топ `agent:112 → agent:UNKNOWN` (n=1214, p=0.2184)
- `membrane_to_action`: топ `membrane:WORKITEM → action:W_Nabellen offertes|COMPLETE` (n=13853, p=0.1172)
- `membrane_to_information_field`: топ `membrane:APPLICATION → information_field:case:AMOUNT_REQ` (n=1, p=0.1667)

## Решения
- Следующий естественный шаг: на ребре A→B посчитать changed Information fields между event i и i+1 внутри кейса.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.5)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5
- Directed edges: E=1694 из 4160 возможных
- Entity field: сущностей=110, рёбер=3129, типов={'agent_to_action': 1178, 'membrane_to_action': 64, 'membrane_to_information_field': 18, 'action_to_action': 175, 'agent_to_agent': 1694}

## Ограничения
- **SPLIT_NOT_TARGET**: split 3+2, цель 7+3
