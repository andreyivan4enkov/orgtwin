# OrgTwin v0.8.8

0.8.8: Sepsis; глобальная сводка мутаций Information по всем directed рёбрам (не только top-15).

Рецепт: `agent_rules`. Конфиг: `configs/diagnostic/v0.8.8.json`.
Политика (по CE holdout): **softmax**.

## Holdout next-step
| Метрика | counts | softmax |
|---------|------|------|
| next-step | 0.7187 | 0.7208 |
| top-3 | 0.9944 | 0.9959 |
| CE | 0.6885 | 0.6470 |

## Локальные минимумы (fit)
Агентов: 25; с незаменимыми частыми действиями: 5.

- `C`: n=491, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=1
- `?`: n=152, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=1
- `F`: n=95, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=0
- `O`: n=74, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=0
- `G`: n=70, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=0
- `I`: n=58, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=0
- `M`: n=48, H≈0.0000, stuck_frac=1.0000, действий 1/1, уник. частых=0
- `E`: n=362, H≈0.7598, stuck_frac=0.7939, действий 5/5, уник. частых=2

## Directed Edge Field (fit)
Агентов: 25; рёбер: 144 / 600; плотность: 0.2400.

- `A → C`: n=438, Pout=0.4011, Pin=0.8975, asym=-0.3989, H_from=2.3878, top_changed=InfectionSuspected
- `A → B`: n=401, Pout=0.3672, Pin=0.4402, asym=0.0135, H_from=2.3878, top_changed=Leucocytes
- `C → A`: n=392, Pout=0.8000, Pin=0.5513, asym=0.3989, H_from=0.9063, top_changed=InfectionSuspected
- `B → A`: n=307, Pout=0.3537, Pin=0.4318, asym=-0.0135, H_from=2.8828, top_changed=LacticAcid
- `B → E`: n=288, Pout=0.3318, Pin=0.7956, asym=0.3187, H_from=2.8828, top_changed=CRP
- `E → ?`: n=151, Pout=0.9869, Pin=0.9934, asym=0.9869, H_from=0.1005
- `F → B`: n=78, Pout=0.8387, Pin=0.0856, asym=0.8007, H_from=0.7503, top_changed=Leucocytes
- `C → B`: n=65, Pout=0.1327, Pin=0.0714, asym=0.1119, H_from=0.9063, top_changed=Leucocytes

## Мутации Information на всех рёбрах (fit)
Кандидатов полей: 27.  
Рёбер с мутацией: 49 / 144 (доля 0.3403).  
Handover с мутацией: 2640 / 3262 (доля 0.8093).  
Взвешенное среднее числа полей: 8.6933.  
Глобальный топ полей: `Leucocytes` (725), `CRP` (668), `InfectionSuspected` (485), `DiagnosticBlood` (485), `DisfuncOrg` (485), `SIRSCritTachypnea` (485).

Топ рёбер по mutation_mass (avg_n × n):
- `A → C`: n=438, avg_n=23.6833, mass=10373.3000, top=InfectionSuspected
- `C → A`: n=392, avg_n=23.6667, mass=9277.3333, top=InfectionSuspected
- `A → B`: n=401, avg_n=1.9740, mass=791.5844, top=Leucocytes
- `L → C`: n=31, avg_n=23.5517, mass=730.1034, top=InfectionSuspected
- `B → A`: n=307, avg_n=1.6711, mass=513.0266, top=LacticAcid
- `B → E`: n=288, avg_n=1.0000, mass=288.0000, top=CRP

По tertile handover_count:
- `low` (n=1…2): рёбер 5/48, доля=0.1042
- `mid` (n=2…10): рёбер 10/48, доля=0.2083
- `high` (n=10…438): рёбер 34/48, доля=0.7083

## Entity-Edge Layer (fit)
Сущностей: 98; рёбер: 506.  
Типы сущностей: {'agent': 25, 'action': 16, 'information_field': 32, 'membrane': 25}.  
Типы рёбер: {'agent_to_action': 40, 'membrane_to_action': 40, 'membrane_to_information_field': 180, 'action_to_action': 102, 'agent_to_agent': 144}.

- `action_to_action`: топ `action:Leucocytes|complete → action:CRP|complete` (n=795, p=0.5268)
- `agent_to_action`: топ `agent:B → action:Leucocytes|complete` (n=1530, p=0.4203)
- `agent_to_agent`: топ `agent:A → agent:C` (n=438, p=0.4011)
- `membrane_to_action`: топ `membrane:B → action:Leucocytes|complete` (n=1530, p=0.4203)
- `membrane_to_information_field`: топ `membrane:? → information_field:case:concept:name` (n=1, p=0.2000)

## Решения
- Сводка mutation по всем ненулевым рёбрам: доля, mass, tertile handover_count.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.8)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11
- Directed edges: E=144 из 600 возможных
- Entity field: сущностей=98, рёбер=506, типов={'agent_to_action': 40, 'membrane_to_action': 40, 'membrane_to_information_field': 180, 'action_to_action': 102, 'agent_to_agent': 144}

## Ограничения
—
