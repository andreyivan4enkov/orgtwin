# Технический долг / 技术债

Только факты. Два контура: [docs/CONTOURS.md](../docs/CONTOURS.md).

---

## 0. Два контура (с 0.9.1)

| | RU | 中文 |
|--|----|------|
| **Диагност** | `run_diagnostic.py`, `configs/diagnostic/`, `reports/diagnostic/` | 商业诊断轨 |
| **Симулятор** | `run_simulator.py`, `configs/simulator/`, `reports/simulator/` | 科研仿真轨 |
| Факт | v0.8.0 agent_rules = эталон диагноста | 0.8.0 诊断范例 |
| Факт | v0.1–0.7 в `reports/` — до разделения | 旧报告在根目录 |

---

## 1. Скрипты

| | RU | 中文 |
|--|----|------|
| Диагност | `run_diagnostic.py` | 诊断入口 |
| Симулятор | `run_simulator.py` | 仿真入口 |
| Legacy | `run_experiment.py`, `scripts/legacy/` | 兼容 |

---

## 2. Timing — только симулятор

| | RU | 中文 |
|--|----|------|
| Факт | Ridge(dt) + case-head; Σdt Spearman ≈ 0 | 见 v0.3–0.4 |
| Статус | Не KPI диагноста | 非产品指标 |

---

## 3. FEP / sim — только симулятор

| | RU | 中文 |
|--|----|------|
| Факт | FEP ≈ softmax next-step на BPIC2012 | 见 0.6–0.7 |
| Статус | Вне диагноста | 诊断轨不含 |
| v0.10 | `queue_des` — честная нагрузка; legacy batch-sim для воспроизведения v0.3–0.7 | 队列 DES vs 旧 batch |

---

## 4. Доноры

| | RU | 中文 |
|--|----|------|
| Диагност | Hospital 2011 (v0.8.0) | 科室≠个人 |
| Симулятор | BPIC2012; BPIC2019 в конфиге = R&D | 见左 |
| Открыто | Закрытый контур заказчика; слот занятости | 无负载槽 |

---

## Приоритет диагноста

1. Локальные правила + holdout CE — v0.8.0.  
2. Застревание / незаменимость — `local_minima.py`.  
3. Не обещать: ×2 поток, weekly_corr, sim duration.  
4. Симулятор — отдельный pitch.
