# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/) + секция **中文** на каждую версию.  
Версии: [Semantic Versioning](https://semver.org/lang/ru/) — `MAJOR.MINOR.PATCH`.

Правило: каждый эксперимент → новая версия + `reports/LAB_JOURNAL.md`. Старые прогоны не переписываем.  
约定：每次实验 → 新版本 + 实验日志；不回写旧跑数。

Текст ниже — **только факты** из прогонов на BPIC2012 (split 3+2), без спекуляций.  
以下仅陈述 BPIC2012（3+2 划分）实测事实。

---

## [0.5.0] — 2026-09-03

### Русский

#### Добавлено
- Политика FEP / активный вывод (`src/orgtwin/policy/fep.py`):  
  \(G = \mathrm{Risk} + \mathrm{Ambiguity} - \mathrm{Habit}\), \(\pi \propto \exp(-\gamma G)\); Dirichlet–Categorical (без logistic regression).
- A/B Softmax vs FEP: `scripts/run_v0_5_0.py`, артефакты `reports/run_v0.5.0.*`.
- `FEPPolicyConfig` в `ExperimentConfig`.

#### Изменено
- Симулятор и `evaluate` принимают Softmax или FEP (`policy_kind`).

#### Протестировано (holdout, raw)
| | Softmax | FEP/EFE |
|--|---------|---------|
| next-step accuracy | 0.5504 | 0.4660 |
| top-3 | 0.9112 | 0.8465 |
| cross-entropy (nats) | 1.0443 | 1.7636 |
| weekly_events_corr | 0.9216 | 0.8676 |
| sim wall (с) | 9.0 | 10.3 |

Победитель по next-step и weekly_corr в этом прогоне: **softmax**.  
Константы FEP прогона: α=0.5, γ=2.0, веса risk/ambiguity/habit = 1/1/1.  
Тег GitHub: `v0.5.0`.

### 中文

#### 新增
- FEP / 主动推理策略（`src/orgtwin/policy/fep.py`）：  
  \(G = \mathrm{Risk} + \mathrm{Ambiguity} - \mathrm{Habit}\)，\(\pi \propto \exp(-\gamma G)\)；Dirichlet–Categorical（无逻辑回归）。
- Softmax 与 FEP 的 A/B：`scripts/run_v0_5_0.py`，产物 `reports/run_v0.5.0.*`。
- `ExperimentConfig` 中的 `FEPPolicyConfig`。

#### 变更
- 仿真器与 `evaluate` 同时支持 Softmax 或 FEP（`policy_kind`）。

#### 已测试（holdout，raw）
| | Softmax | FEP/EFE |
|--|---------|---------|
| next-step accuracy | 0.5504 | 0.4660 |
| top-3 | 0.9112 | 0.8465 |
| cross-entropy (nats) | 1.0443 | 1.7636 |
| weekly_events_corr | 0.9216 | 0.8676 |
| 仿真耗时 (s) | 9.0 | 10.3 |

本跑次 next-step 与 weekly_corr 胜者：**softmax**。  
FEP 常量：α=0.5，γ=2.0，risk/ambiguity/habit 权重 = 1/1/1。  
GitHub 标签：`v0.5.0`。

---

## [0.4.0] — 2026-09-03

### Русский

#### Добавлено
- Пакет/репозиторий **OrgTwin** (`orgtwin`); semver: `VERSION`, `pyproject.toml`, CHANGELOG.
- Батч-encode признаков в симуляции.
- Калибровка длительности: масштабирование dt под case-level duration head (зафиксировано как не эмерджентность).
- Стресс-тест: отключение топ-3 агентов по fit-нагрузке.
- Пайплайн `scripts/run_v0_4_0.py`, артефакты `reports/run_v0.4.0.*`.

#### Изменено
- Имя пакета `b2b_sim` → `orgtwin`.

#### Протестировано (holdout)
| Режим | next-step | top-3 | weekly_corr | dur Spearman | wall (с) |
|-------|-----------|-------|-------------|--------------|----------|
| baseline_raw | 0.5504 | 0.9112 | 0.9216 | 0.0024 | 10.4 |
| calibrated | 0.5504 | 0.9112 | 0.8574 | 0.2245 | 11.0 |
| stress_top3_calibrated | 0.5504 | 0.9112 | 0.8420 | 0.2197 | 13.4 |

Отключённые агенты в стрессе: `112`, `UNKNOWN`, `11189`.  
Откат прунинга `O_DECLINED` на мембране (APPLICATION, OFFER).  
Тег GitHub: `v0.4.0`.

### 中文

#### 新增
- 包/仓库 **OrgTwin**（`orgtwin`）；semver：`VERSION`、`pyproject.toml`、CHANGELOG。
- 仿真中批量特征编码。
- 时长校准：按 case-level duration head 缩放 dt（记录为非涌现）。
- 压力测试：按拟合负荷关闭 top-3 智能体。
- 流水线 `scripts/run_v0_4_0.py`，产物 `reports/run_v0.4.0.*`。

#### 变更
- 包名 `b2b_sim` → `orgtwin`。

#### 已测试（holdout）
| 模式 | next-step | top-3 | weekly_corr | dur Spearman | 耗时 (s) |
|------|-----------|-------|-------------|--------------|----------|
| baseline_raw | 0.5504 | 0.9112 | 0.9216 | 0.0024 | 10.4 |
| calibrated | 0.5504 | 0.9112 | 0.8574 | 0.2245 | 11.0 |
| stress_top3_calibrated | 0.5504 | 0.9112 | 0.8420 | 0.2197 | 13.4 |

压力测试关闭的智能体：`112`、`UNKNOWN`、`11189`。  
膜上恢复了 `O_DECLINED` 剪枝回滚（APPLICATION、OFFER）。  
GitHub 标签：`v0.4.0`。

---

## [0.3.0] — 2026-09-03

### Русский

#### Добавлено
- Softmax + Ridge(`log1p(dt)`) + case-level duration head.
- `ExperimentConfig`, LAB_JOURNAL, failures JSON.
- Скрипты-архив: `run_pipeline_v1.py`, `run_pipeline_v2.py`.

#### Зафиксированные результаты / отказы
- Fit event-dt Spearman: **0.853**; baseline median(agent,action): **0.796**.
- Holdout next-step: **0.550**, top-3: **0.911**, weekly_corr: **0.873**.
- Эмерджентная сумма dt: Spearman **≈ −0.001**.
- Case-level head holdout Spearman: **0.229**.
- Прогон `max_steps=80` прерван по wall-time (поштучный encode); в финале `max_steps=40`.
- `latency_noise` выключен (=1.0).

### 中文

#### 新增
- Softmax + Ridge(`log1p(dt)`) + case 级时长头。
- `ExperimentConfig`、LAB_JOURNAL、failures JSON。
- 归档脚本：`run_pipeline_v1.py`、`run_pipeline_v2.py`。

#### 已记录结果 / 失败
- 拟合 event-dt Spearman：**0.853**；中位数基线：**0.796**。
- Holdout next-step：**0.550**，top-3：**0.911**，weekly_corr：**0.873**。
- 涌现式 Σdt Spearman：**≈ −0.001**。
- Case 级头 holdout Spearman：**0.229**。
- `max_steps=80` 因耗时中止；最终使用 `max_steps=40`。
- `latency_noise` 关闭（=1.0）。

---

## [0.2.0] — 2026-09-03

### Русский

#### Добавлено
- Multinomial logistic (softmax) P(Action | Information, agent).
- Маска мембраны роли; prune `min_support=30`.

#### Протестировано (holdout)
- next-step accuracy: **0.551**; top-3: **0.911**; weekly_corr: **0.955**.
- Fit action accuracy: **0.563**.

### 中文

#### 新增
- 多项逻辑回归（softmax）P(Action | Information, agent)。
- 角色膜掩码；剪枝 `min_support=30`。

#### 已测试（holdout）
- next-step：**0.551**；top-3：**0.911**；weekly_corr：**0.955**。
- 拟合动作准确率：**0.563**。

---

## [0.1.0] — 2026-09-03

### Русский

#### Добавлено
- Донор BPIC2012; IR Information/Action; эмпирические счётчики; первый fit/holdout.

#### Протестировано
- weekly_events_corr: **−0.483** (относительное время симуляции).
- Fit: 7427 кейсов / 149330 событий; holdout: 5658 / 112847.
- Нейроавтоматы: 65 (1 resource = 1 агент); Action catalog: 36.

### 中文

#### 新增
- 数据源 BPIC2012；Information/Action IR；经验计数；首次 fit/holdout。

#### 已测试
- weekly_events_corr：**−0.483**（仿真使用相对时间）。
- Fit：7427 案例 / 149330 事件；holdout：5658 / 112847。
- 神经自动机：65（1 resource = 1 智能体）；Action 目录：36。
