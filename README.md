# OrgTwin

**Цифровой двойник операционного организма компании.**

OrgTwin моделирует фирму как плоский граф агентов: всё взаимодействие сводится к примитивам **Information** (что записано / видно) и **Action** (какая мутация информации допустима). Симуляция In Silico учится на событиийном следе одной организации и проверяется на holdout.

Понятно системщику: process mining + агентная симуляция + softmax/регрессия.  
Понятно предпринимателю: «двойник процессов» — что будет с потоком дел, если поменять людей, правила или нагрузку — до эксперимента на живых.

## Версии

См. [CHANGELOG.md](CHANGELOG.md) и файл `VERSION`. Текущая: **0.5.0**.

Правило: каждый эксперимент — **новая версия**, старые артефакты не переписываем.

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
# или: .venv/bin/pip install -r requirements.txt && PYTHONPATH=src ...

# скачать донор BPIC2012 (если нет data/raw/*.xes)
.venv/bin/python scripts/download_bpic2012.py

# A/B: Softmax vs FEP (Friston EFE)
.venv/bin/python scripts/run_v0_5_0.py
```

Журнал констант и провалов: `reports/LAB_JOURNAL.md`.

## Структура

- `src/orgtwin/` — ядро (IR, ingest, policy, sim, eval, config)
- `scripts/run_vX_Y_Z.py` — воспроизводимый прогон версии
- `reports/` — метрики и журналы (не SoT кода)
- `data/raw/` — донор (крупные XES в git не кладём; см. DOI в SOURCE.md)

## Донор v0.x

BPI Challenge 2012 — один финансовый институт. DOI в `data/raw/SOURCE.md`.
