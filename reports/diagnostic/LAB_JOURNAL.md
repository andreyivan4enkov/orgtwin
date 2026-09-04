

---

## v0.8.1 — run_experiment (2026-09-03T14:08:31.003256+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.1.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
- Медицинский донор #2: Sepsis, не склеивать с Hospital2011/BPIC2012
- role_mode=agent: мембрана = отделение (org:group)
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.1)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11

### Артефакты
- `reports/run_v0.8.1.md`, `run_v0.8.1_full.json`


---

## v0.8.2 — run_experiment (2026-09-03T14:09:10.638985+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.2.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
- Сопоставление: BPIC2012 agent_rules vs Hospital/Sepsis
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.2)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5

### Артефакты
- `reports/run_v0.8.2.md`, `run_v0.8.2_full.json`


---

## v0.8.0 — run_experiment (2026-09-03T15:00:10.925172+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.0.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.6243750946826239, "softmax": 0.629450083320709}, "top3_accuracy": {"counts": 0.849871231631571, "softmax": 0.861687623087411}, "cross_entropy": {"counts": 2.2233572535629285, "softmax": 1.2965110799102615}, "n": {"counts": 13202, "softmax": 13202}}

### Решения
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

### Артефакты
- `reports/run_v0.8.0.md`, `run_v0.8.0_full.json`


---

## v0.8.1 — run_experiment (2026-09-03T15:00:16.932953+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.1.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
- Медицинский донор #2: Sepsis, не склеивать с Hospital2011/BPIC2012
- role_mode=agent: мембрана = отделение (org:group)
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.1)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11
- Directed edges: E=144 из 600 возможных

### Артефакты
- `reports/run_v0.8.1.md`, `run_v0.8.1_full.json`


---

## v0.8.2 — run_experiment (2026-09-03T15:01:02.438692+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.2.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
- Сопоставление: BPIC2012 agent_rules vs Hospital/Sepsis
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.2)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5
- Directed edges: E=1694 из 4160 возможных

### Артефакты
- `reports/run_v0.8.2.md`, `run_v0.8.2_full.json`


---

## v0.8.0 — run_experiment (2026-09-03T15:09:02.834462+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.0.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.6243750946826239, "softmax": 0.629450083320709}, "top3_accuracy": {"counts": 0.849871231631571, "softmax": 0.861687623087411}, "cross_entropy": {"counts": 2.2233572535629285, "softmax": 1.2965110799102615}, "n": {"counts": 13202, "softmax": 13202}}

### Решения
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

### Артефакты
- `reports/run_v0.8.0.md`, `run_v0.8.0_full.json`


---

## v0.8.1 — run_experiment (2026-09-03T15:09:10.408053+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.1.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
- Медицинский донор #2: Sepsis, не склеивать с Hospital2011/BPIC2012
- role_mode=agent: мембрана = отделение (org:group)
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.1)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11
- Directed edges: E=144 из 600 возможных
- Entity field: сущностей=98, рёбер=506, типов={'agent_to_action': 40, 'membrane_to_action': 40, 'membrane_to_information_field': 180, 'action_to_action': 102, 'agent_to_agent': 144}

### Артефакты
- `reports/run_v0.8.1.md`, `run_v0.8.1_full.json`


---

## v0.8.2 — run_experiment (2026-09-03T15:10:25.044038+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.2.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
- Сопоставление: BPIC2012 agent_rules vs Hospital/Sepsis
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.2)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5
- Directed edges: E=1694 из 4160 возможных
- Entity field: сущностей=110, рёбер=3129, типов={'agent_to_action': 1178, 'membrane_to_action': 64, 'membrane_to_information_field': 18, 'action_to_action': 175, 'agent_to_agent': 1694}

### Артефакты
- `reports/run_v0.8.2.md`, `run_v0.8.2_full.json`


---

## v0.8.3 — run_experiment (2026-09-03T15:36:42.172876+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.3.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.6243750946826239, "softmax": 0.629450083320709}, "top3_accuracy": {"counts": 0.849871231631571, "softmax": 0.861687623087411}, "cross_entropy": {"counts": 2.2233572535629285, "softmax": 1.2965110799102615}, "n": {"counts": 13202, "softmax": 13202}}

### Решения
- Следующий естественный шаг: на ребре A→B посчитать changed Information fields между event i и i+1 внутри кейса.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.3)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.2965 < 2.2234) — политика = softmax
- Диагностика: агентов=33, незаменимых частых действий (уник. носитель)=61
- Directed edges: E=184 из 1056 возможных
- Entity field: сущностей=596, рёбер=4793, типов={'agent_to_action': 487, 'membrane_to_action': 453, 'membrane_to_information_field': 1186, 'action_to_action': 2483, 'agent_to_agent': 184}

### Артефакты
- `reports/run_v0.8.3.md`, `run_v0.8.3_full.json`


---

## v0.8.4 — run_experiment (2026-09-03T16:01:05.118654+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.4.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
- Следующий естественный шаг: на ребре A→B посчитать changed Information fields между event i и i+1 внутри кейса.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.4)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11
- Directed edges: E=144 из 600 возможных
- Entity field: сущностей=98, рёбер=506, типов={'agent_to_action': 40, 'membrane_to_action': 40, 'membrane_to_information_field': 180, 'action_to_action': 102, 'agent_to_agent': 144}

### Артефакты
- `reports/run_v0.8.4.md`, `run_v0.8.4_full.json`


---

## v0.8.5 — run_experiment (2026-09-03T16:02:29.273226+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.5.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
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

### Артефакты
- `reports/run_v0.8.5.md`, `run_v0.8.5_full.json`


---

## v0.8.6 — run_experiment (2026-09-03T16:03:39.184263+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.6.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
- Следующий естественный шаг: на ребре A→B посчитать changed Information fields между event i и i+1 внутри кейса.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.6)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (0.6470 < 0.6885) — политика = softmax
- Диагностика: агентов=25, незаменимых частых действий (уник. носитель)=11
- Directed edges: E=144 из 600 возможных
- Entity field: сущностей=98, рёбер=506, типов={'agent_to_action': 40, 'membrane_to_action': 40, 'membrane_to_information_field': 180, 'action_to_action': 102, 'agent_to_agent': 144}

### Артефакты
- `reports/run_v0.8.6.md`, `run_v0.8.6_full.json`


---

## v0.8.7 — run_experiment (2026-09-03T16:04:55.112608+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.7.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
- Следующий естественный шаг: на ребре A→B посчитать changed Information fields между event i и i+1 внутри кейса.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.7)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5
- Directed edges: E=1694 из 4160 возможных
- Entity field: сущностей=110, рёбер=3129, типов={'agent_to_action': 1178, 'membrane_to_action': 64, 'membrane_to_information_field': 18, 'action_to_action': 175, 'agent_to_agent': 1694}

### Артефакты
- `reports/run_v0.8.7.md`, `run_v0.8.7_full.json`


---

## v0.8.8 — run_experiment (2026-09-03T16:28:19.469912+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.8.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.7187039764359352, "softmax": 0.7207658321060383}, "top3_accuracy": {"counts": 0.9944035346097202, "softmax": 0.9958762886597938}, "cross_entropy": {"counts": 0.6885138818354957, "softmax": 0.6470277832273592}, "n": {"counts": 3395, "softmax": 3395}}

### Решения
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

### Артефакты
- `reports/run_v0.8.8.md`, `run_v0.8.8_full.json`


---

## v0.8.9 — run_experiment (2026-09-03T16:29:40.161806+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.9.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.545734672544653, "softmax": 0.5503704040358133}, "top3_accuracy": {"counts": 0.892378312048357, "softmax": 0.911239376448666}, "cross_entropy": {"counts": 1.662298236418105, "softmax": 1.040568064133424}, "n": {"counts": 110015, "softmax": 110015}}

### Решения
- Сводка mutation по всем ненулевым рёбрам: доля, mass, tertile handover_count.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.9)
- package_version=0.10.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.0406 < 1.6623) — политика = softmax
- Диагностика: агентов=65, незаменимых частых действий (уник. носитель)=5
- Directed edges: E=1694 из 4160 возможных
- Entity field: сущностей=110, рёбер=3129, типов={'agent_to_action': 1178, 'membrane_to_action': 64, 'membrane_to_information_field': 18, 'action_to_action': 175, 'agent_to_agent': 1694}

### Артефакты
- `reports/run_v0.8.9.md`, `run_v0.8.9_full.json`


---

## v0.8.10 — run_experiment (2026-09-03T16:33:41.919143+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/diagnostic/v0.8.10.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.6243750946826239, "softmax": 0.629450083320709}, "top3_accuracy": {"counts": 0.849871231631571, "softmax": 0.861687623087411}, "cross_entropy": {"counts": 2.2233572535629285, "softmax": 1.2965110799102615}, "n": {"counts": 13202, "softmax": 13202}}

### Решения
- Сводка mutation по всем ненулевым рёбрам: доля, mass, tertile handover_count.
- Контур diagnostic: agent_rules (счётчики + A/B softmax по CE).
- Контур=diagnostic; scripts/run_diagnostic.py (версия 0.8.10)
- package_version=0.11.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.2965 < 2.2234) — политика = softmax
- Диагностика: агентов=33, незаменимых частых действий (уник. носитель)=61
- Directed edges: E=184 из 1056 возможных
- Entity field: сущностей=596, рёбер=4793, типов={'agent_to_action': 487, 'membrane_to_action': 453, 'membrane_to_information_field': 1186, 'action_to_action': 2483, 'agent_to_agent': 184}

### Артефакты
- `reports/run_v0.8.10.md`, `run_v0.8.10_full.json`
