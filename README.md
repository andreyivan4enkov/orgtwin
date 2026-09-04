# OrgTwin

| | |
|---|---|
| **RU** | Цифровой двойник операционного организма — **два независимых контура** |
| **中文** | 企业运营数字孪生 — **两条独立轨道** |

Подробно: [docs/CONTOURS.md](docs/CONTOURS.md).

---

## Диагност (коммерческий контур)

Из событийного лога: **локальные правила** \(P(\text{действие}\mid\text{вход}, \text{агент})\), holdout next-step, **застревание** и незаменимые действия.

Softmax здесь — `LogisticRegression` на `(prev, amount_bin, agent)`, не LLM. Вторая политика (softmax) только если CE на holdout лучше счётчиков.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/python scripts/download_hospital2011.py
.venv/bin/python scripts/run_diagnostic.py --config configs/diagnostic/v0.8.0.json
```

Отчёты: `reports/diagnostic/`. Эталон: [reports/diagnostic/run_v0.8.0.md](reports/diagnostic/run_v0.8.0.md) (Hospital, next **0.629**, диагност локальных минимумов).

**Не входит:** FEP, симуляция нагрузки, timing, ×2 поток (нет слота занятости).

---

## Симулятор (научный контур)

R&D: softmax vs FEP, Ridge(dt) — **legacy batch-sim**. Честный стресс нагрузки — **очередь** (v0.10).

```bash
.venv/bin/python scripts/download_bpic2012.py
.venv/bin/python scripts/run_simulator.py --config configs/simulator/v0.7.0.json   # legacy
.venv/bin/python scripts/run_queue_stress.py   # ×1 vs ×2, метрика max_queue
```

Документация: [docs/SIMULATOR_HONEST.md](docs/SIMULATOR_HONEST.md). История решений: [docs/HISTORY.md](docs/HISTORY.md).

Отчёты: `reports/simulator/`. Архив v0.1–v0.7 — в корне `reports/`.

---

## Версия

**0.11.0** — полный PoC: диагност + очередь ×1/×2/слот+1 ([CHANGELOG.md](CHANGELOG.md)).

```bash
.venv/bin/python scripts/run_poc.py
# отчёт: reports/poc/POC.md
```

---

## Веб-интерфейс

Самохостируемый UI: карта организма, правила агентов, поток кейсов, срезы нагрузки, режим проектирования.
Спека: [docs/UI_SPEC.md](docs/UI_SPEC.md).

```bash
# API
.venv/bin/pip install -e .
.venv/bin/uvicorn apps.api.main:app --reload --app-dir . --port 8000

# UI (прокси /api → :8000)
cd web && npm install && npm run dev
# http://127.0.0.1:5173
```

Или целиком:

```bash
docker compose up --build
# UI http://127.0.0.1:8080  ·  API http://127.0.0.1:8000/api/health
```

Доноры: BPIC2012 / BPIC2019 / Hospital (файлы в `data/raw/`).

---

## Структура

| Путь | Назначение |
|------|------------|
| `src/orgtwin/policy/counts.py`, `diag/local_minima.py` | Диагност |
| `src/orgtwin/sim/queue_des.py`, `sim/engine.py` | Симулятор (очередь + legacy) |
| `configs/diagnostic/`, `configs/simulator/` | Конфиги по контурам |
| `scripts/run_diagnostic.py`, `run_simulator.py` | Точки входа |
| `data/raw/SOURCE.md` | Доноры |

При push/релизе: описание **RU + 中文**, только фacts.
