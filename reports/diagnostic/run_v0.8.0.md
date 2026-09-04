# OrgTwin v0.8.0

0.8.0: Hospital BPIC2011; agent_rules; org:group; split 7+3.

Рецепт: `agent_rules`. Конфиг: `configs/diagnostic/v0.8.0.json`.
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

## Directed Edge Field (fit)
Агентов: 33; рёбер: 184 / 1056; плотность: 0.1742.

- `Nursing ward → General Lab Clinical Chemistry`: n=1144, Pout=0.5652, Pin=0.4460, asym=0.1858, H_from=2.4740
- `General Lab Clinical Chemistry → Nursing ward`: n=977, Pout=0.3794, Pin=0.4759, asym=-0.1858, H_from=2.6549
- `Medical Microbiology → General Lab Clinical Chemistry`: n=435, Pout=0.9932, Pin=0.1696, asym=0.8794, H_from=0.0699
- `General Lab Clinical Chemistry → Internal Specialisms clinic`: n=426, Pout=0.1654, Pin=0.7220, asym=-0.0258, H_from=2.6549
- `Internal Specialisms clinic → Nursing ward`: n=377, Pout=0.6379, Pin=0.1836, asym=0.6147, H_from=1.6679
- `General Lab Clinical Chemistry → Obstetrics & Gynaecology clinic`: n=307, Pout=0.1192, Pin=0.3473, asym=-0.2098, H_from=2.6549
- `Obstetrics & Gynaecology clinic → General Lab Clinical Chemistry`: n=305, Pout=0.3290, Pin=0.1189, asym=0.2098, H_from=2.6063
- `General Lab Clinical Chemistry → Medical Microbiology`: n=293, Pout=0.1138, Pin=0.6689, asym=-0.8794, H_from=2.6549

## Entity-Edge Layer (fit)
Сущностей: 596; рёбер: 4793.  
Типы сущностей: {'agent': 33, 'action': 420, 'information_field': 128, 'membrane': 15}.  
Типы рёбер: {'agent_to_action': 487, 'membrane_to_action': 453, 'membrane_to_information_field': 1186, 'action_to_action': 2483, 'agent_to_agent': 184}.

- `action_to_action`: топ `action:aanname laboratoriumonderzoek|complete → action:aanname laboratoriumonderzoek|complete` (n=2366, p=0.5410)
- `agent_to_action`: топ `agent:General Lab Clinical Chemistry → action:aanname laboratoriumonderzoek|complete` (n=4048, p=0.1505)
- `agent_to_agent`: топ `agent:Nursing ward → agent:General Lab Clinical Chemistry` (n=1144, p=0.5652)
- `membrane_to_action`: топ `membrane:86 → action:aanname laboratoriumonderzoek|complete` (n=4051, p=0.1493)
- `membrane_to_information_field`: топ `membrane:13 → information_field:Activity code` (n=1, p=0.0110)

## Решения
- Критический путь agent_rules: счётчики + A/B softmax по CE
- FEP / case-head / stress / prune вне рецепта
- Второй организм HOSPITAL2011, не склеивать с BPIC2012
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.0)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.2965 < 2.2234) — политика = softmax
- Диагностика: агентов=33, незаменимых частых действий (уник. носитель)=61
- Directed edges: E=184 из 1056 возможных
- Entity field: сущностей=596, рёбер=4793, типов={'agent_to_action': 487, 'membrane_to_action': 453, 'membrane_to_information_field': 1186, 'action_to_action': 2483, 'agent_to_agent': 184}

## Ограничения
—
