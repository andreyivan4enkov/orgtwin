# Лабораторный журнал (обязательная фиксация)

Правило: каждое решение, константа, провал и «сработало» — сюда. Без устных договорённостей.

---

## Донор (не менять без новой строки)

| Поле | Значение |
|---|---|
| Датасет | BPI Challenge 2012 |
| DOI | `10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f` |
| Организм | один NL financial institute (кредитный процесс) |
| Окно сырых данных | 2011-10-01 → 2012-03-14 (~5.5 мес) |
| MD5 xes.gz | `74c7ba9aba85bfcb181a22c9d565e5b5` |
| Почему не склеиваем с BPIC2020/CERT/Gladden | подмена «одного организма» |

**Ограничение донора:** нет явных HR-шоков (болезнь/смерть); lifecycle A_/O_/W_ + `org:resource` + `AMOUNT_REQ`.

---

## Целевой протокол vs факт

| | Цель (ТЗ) | Факт на BPIC2012 |
|---|---|---|
| Fit / holdout | 7 мес / 3 мес | **3 / 2** (`SplitConfig`) |
| Причина | лог короче года | пропорция сохранена, абсолют нет |

Константы: `fit_months=3`, `holdout_months=2`, `target_fit_months=7`, `target_holdout_months=3`.

---

## v0 — эмпирические счётчики (ПРОВАЛ по времени)

### Решение
- Локальные правила = `P(action | prev_activity, amount_bin)` по счётчикам на агента.
- Hand-over: счётчики смен resource; stay_weight = max(1, sum(out)//2).
- Latency: среднее dt по (agent, action); шум U(0.7, 1.3).
- Симуляция: относительное `t_sec` от 0, weekly от `t0=hold.min()` — **ошибка календаря**.

### Константы v0
- `min_agent_events=5` (в вызове; в `decompose_org` дефолт 20 не использовался жёстко)
- `max_steps_per_case=40`
- `seed=42`
- amount bins: `pd.qcut(..., q=4)`
- dt filter: `[0, 30 дней)`

### Метрики (факт)
- weekly_corr ≈ **−0.48** (провал)
- case_duration_mape огромный (~7000) — бессмысленная шкала
- top20_action_overlap = 16/20 (приемлемо)

### Вывод
Эмпирика + кривой календарь = подлог «симуляции времени». Нужна обучаемая политика и абсолютные timestamps.

---

## v1 — softmax (ЧАСТИЧНЫЙ УСПЕХ)

### Решение
- One-Hot(`prev_activity`, `amount_bin`, `agent`) → `LogisticRegression` softmax.
- Loss-прокси аудита: `F ≈ CE + λ H`, `λ=0.05`.
- Мембрана роли = mask support(action|role); прунинг `min_support=30`.
- Hand-over: `stay = sum(outgoing)`; P(stay)=0.5 по построению.
- Latency: **медиана** dt|(agent,action); шум U(0.7,1.3) оставлен.
- Timestamps: case start = реальный first event holdout.

### Константы v1 (зафиксированы в `config/constants.py`)
| Имя | Значение | Зачем |
|---|---|---|
| `lambda_entropy` | 0.05 | λ в CE+λH; **не тюнился** |
| `max_iter` | 250 | lbfgs; на sklearn 1.9 снят `multi_class=` (API break) |
| `C` | 1.0 | L2 inverse strength |
| `prune_min_support` | 30 | редкие Action с мембраны |
| `amount_quantiles` | 0,0.25,0.5,0.75,1 | бины суммы |
| `max_steps_per_case` | 40 | обрезка траектории |
| `latency_noise` | U(0.7, 1.3) | **подозрение на убийство Spearman** |
| `dt_max_sec` | 30 дней | выбросы |
| `default_latency_sec` | 3600 | fallback 1ч |
| `seed` | 42 | |

### Инциденты / баги
1. **sklearn 1.9:** `multi_class="multinomial"` → `TypeError`. Фикс: убрать аргумент (multiclass и так softmax).
2. **SyntaxWarning** в `run_v1.py` из-за `\(` в f-string markdown — косметика.
3. **Обучение ~5 мин** на 149k строк — приемлемо, но медленно; не кэшировали модель.
4. Роль агента = argmax префикса A/O/W по его событиям — **грубо**: один человек может делать смешанные префиксы; APPLICATION-мембрана всё ещё содержит часть W_/O_ из доминанты агента.

### Метрики v1 (факт)
| Метрика | Значение | Вердикт |
|---|---|---|
| fit_action_accuracy | 0.563 | ок для 36 классов |
| holdout next-step acc | **0.551** | ок |
| holdout top-3 | **0.911** | сильно |
| weekly_events_corr | **+0.955** | успех vs v0 |
| case_duration Spearman | **0.004** | ПРОВАЛ |
| case_duration log-MAE | 4.18 | плохо |
| top20 overlap | 15 | чуть хуже v0 |
| terminal shares | CANCEL/DECLINE завышены, APPROVED занижен | смещение политики |

### Гипотезы провала длительности (к проверке в v2)
1. Шум U(0.7,1.3) уничтожает ранги.
2. Медиана(agent,action) игнорирует `prev_activity` / lifecycle.
3. `max_steps=40` ≠ реальная длина кейса → сумма dt не wall-clock кейса.
4. Реальные кейсы содержат длинные простои, не привязанные к (agent,action) равномерно.
5. Симуляция генерирует меньше событий (84k vs 113k hold) — ранний terminal / мало шагов.

### Прунинг (факт)
Срезаны редкие: `A_ACTIVATED|COMPLETE`, `O_DECLINED|COMPLETE`, часть W_SCHEDULE — возможно ухудшило терминалы DECLINED на симе (нужно сверить; O_DECLINED убран с APPLICATION/OFFER).

---

## Инцидент 2026-09-03 — зависший v2 (ПЕРЕД успешным прогоном)

| | |
|---|---|
| Симптом | `run_pipeline_v2.py` >15 мин на 98% CPU без новой строки в логе |
| Причина | `DataFrame.apply(action_name_from_row)` на ~150k–260k строк в `prepare_trace_frame` / eval |
| Фикс | `action_names_vectorized()`; процесс убит (PID 12094/12101) и перезапущен |
| Урок | Любой `apply(axis=1)` на полном BPIC — фиксировать как риск производительности |
| Константа | не менялась; это баг реализации |

---

## v2 — план и доп. фиксы перед прогоном

### Решения
1. Централизовать константы → `src/b2b_sim/config/constants.py`.
2. Модель времени: Ridge на `log1p(dt)` от (`prev_activity`, `action`, `agent`, `amount_bin`); **шум latency = 1.0** (выключить).
3. Сравнивать `max_steps` ∈ {40, 80}.
4. Векторизация Action; solver softmax: **lbfgs → saga** (`tol=1e-3`, `n_jobs=-1`) из-за инцидента зависания/медленности.

### Что считать успехом v2
- Spearman длительностей holdout **> 0.2** (минимальный порог) или явное документирование, почему потолок ниже.
- Не деградировать next-step top-3 ниже 0.85.
- weekly_corr не ниже 0.9.


---

## v2 — факт прогона (2026-09-03T11:04:19.860268+00:00)

### Что изменили относительно v1
- Модель dt: Ridge(log1p(dt) | prev, action, agent, amount_bin), alpha=1.0
- latency_noise выключен (=1.0); в v1 было U(0.7,1.3) — зафиксировано как вероятная причина Spearman≈0
- Прогон max_steps ∈ {40, 80}; выбран 40
- Константы вынесены в `config/constants.py` + дамп JSON

### Timing fit
- event-dt spearman=0.8528739183633671
- baseline median(agent,action) spearman=0.7964418199062618
- case-level head fit spearman=0.22392207385780277

### Holdout (selected)
- next-step acc=0.5503704040358133
- top3=0.911221197109485
- weekly_corr=0.8730268787479802
- emergent duration Spearman=-0.0010959483106119821
- case-level head Spearman=0.2292521383306908
- hit_max_steps=738/5658

### Решения
- Все гиперпараметры сериализованы в experiment_config_v2.json
- Softmax solver=saga tol=0.001 CE+λH λ=0.05 C=1.0 max_iter=250
- Прунинг min_support=30
- Ridge alpha=1.0; latency_noise=[1.0,1.0] (выкл)
- Добавлена case-level Ridge-голова длительности (не эмерджентная сумма dt) — после провала sum(dt) Spearman≈0 при fit_dt Spearman~0.85
- Для run_v2.md max_steps=40 (80 aborted)
- Case-level duration head закрывает порог Spearman>0.2 (0.229) — но это НЕ эмерджентность

### Неудачи / риски
- **SPLIT_NOT_7_3**: Донор ~5.5 мес → используем 3+2, не целевые 7+3
- **PRUNE_MAY_BIAS_TERMINALS**: Срезаны Action: {'APPLICATION': ['A_ACTIVATED|COMPLETE', 'O_DECLINED|COMPLETE', 'W_Completeren aanvraag|COMPLETE'], 'OFFER': ['O_DECLINED|COMPLETE'], 'WORKITEM': ['W_Afhandelen leads|SCHEDULE', 'W_Wijzigen contractgegevens|SCHEDULE']} — риск смещения исходов
- **MAX_STEPS_80_ABORTED**: Прогон max_steps=80 прерван: wall-time (поштучный softmax encode на каждом шаге). Частичный результат max_steps=40: dur_spearman≈-0.001, hit_max=738/5658, next_acc≈0.55. В финальном v2 оставляем только max_steps=40 + case-level duration head.
- **EMERGENT_DURATION_SPEARMAN_BELOW_0_2**: Эмерджентная сумма dt: Spearman=-0.0010959483106119821. Case-level head Spearman=0.2292521383306908. Вывод: хороший event-dt ≠ хороший case wall-clock через симулированную траекторию Action.
- **WEEKLY_CORR_BELOW_0_9**: weekly_events_corr=0.873 < целевых 0.9 (v1 было 0.955 — возможная регрессия от saga/прунинга/смены latency; не тюнилось).

### Артефакты
- `reports/run_v2.md`, `reports/run_v2_full.json`, `reports/holdout_metrics_v2.json`
- `data/derived/failures_v2.json`, `experiment_config_v2.json`, `timing_metrics.json`

### Следующий шаг (v3) — только после записи гипотез
1. Батчить softmax encode в симуляции (иначе max_steps>40 неподъёмен).
2. Не эмерджентность длительности: survival / hazard на шаге ИЛИ калибровка длины траектории под case-head.
3. A/B: saga vs lbfgs при одинаковых константах — проверить регрессию weekly_corr.
4. Не прунить `O_DECLINED` без отдельного прогона (PRUNE_MAY_BIAS_TERMINALS).


---

## v0.4.0 — OrgTwin (2026-09-03T12:14:47.253019+00:00)

### Изменения
- Пакет/бренд: **OrgTwin** (`orgtwin`), semver в VERSION/pyproject/CHANGELOG
- Батч-сима; калибровка dt→case-head; stress top-3

### Метрики (кратко)
{
  "baseline_raw": {
    "wall_sec": 10.433176411999739,
    "next_acc": 0.5503704040358133,
    "dur_sp": 0.002365111923376657,
    "weekly": 0.9215900380017684
  },
  "calibrated": {
    "wall_sec": 11.018476180997823,
    "next_acc": 0.5503704040358133,
    "dur_sp": 0.22446562987699406,
    "weekly": 0.8573853156611383
  },
  "stress_top3_calibrated": {
    "wall_sec": 13.44012197399934,
    "next_acc": 0.5503704040358133,
    "dur_sp": 0.21967442231721024,
    "weekly": 0.8419775498757414
  }
}

### Решения
- Релиз OrgTwin 0.4.0: батч-encode, калибровка dt→case-head, stress top-3 агентов
- Старые run_v0/v1/v2 не перезаписываем
- solver=saga (A/B lbfgs отложен на 0.4.1)
- Откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- Стресс stress_top3_calibrated: disabled=['112', 'UNKNOWN', '11189']
- Калибровка подняла duration Spearman до 0.224 (не эмерджентность — зафиксировано)
- Батч-сима baseline_raw wall=10.4s
- Стресс delta: {'sim_events_delta': 20772, 'weekly_corr_stress': 0.8419775498757414, 'dur_spearman_stress': 0.21967442231721024, 'hit_max_stress': 1262, 'hit_max_base': 760}

### Неудачи
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
- **PRUNE_DECLINED_ROLLED_BACK**: Восстановлены на мембране: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE'] (риск PRUNE_MAY_BIAS_TERMINALS из 0.3.0)

### Артефакты
- `reports/run_v0.4.0.md`, `run_v0.4.0_full.json`


---

## v0.5.0 — FEP vs Softmax (2026-09-03T12:38:22.248105+00:00)

### Изменения
- Политика активного вывода: Dirichlet + EFE (Risk+Ambiguity−Habit), π∝exp(−γG)
- A/B с softmax на одном split; артефакты `*v0.5.0*`

### Сравнение (кратко)
- next_acc: SM=0.5504 FEP=0.4660 (winner=softmax)
- weekly: SM=0.9215900380017684 FEP=0.8675680432440032 (winner=softmax)
- top3: SM=0.9112 FEP=0.8465

### Решения
- Релиз OrgTwin 0.5.0: A/B Softmax vs FEP (EFE Friston)
- Один split 3+2, один seed; timing обучается на softmax-бандле edges, FEP шарит edges
- Калибровка длительности — для справки; сравнение политик по raw next-step и weekly
- Softmax: откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- FEP cfg: α=0.5 γ=2.0 w_r/a/h=1.0/1.0/1.0
- Победитель next-step accuracy: softmax
- Победитель weekly_corr: softmax

### Неудачи
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3

### Артефакты
- `reports/run_v0.5.0.md`, `run_v0.5.0_full.json`


---

## v0.6.0 — FEP parity vs Softmax (2026-09-03T12:56:53.904571+00:00)

### Изменения
- FEP: habit (prev,amount_bin,**agent**) + backoff; C(o|ctx); тюнинг на fit
- Руки: softmax, fep_habit_only, fep_full_efe; сравнение с 0.5.0 crooked

### Holdout next-step
- SM=0.5503704040358133 habit=0.5508157978457483 full=0.5483797663954916 crooked05=0.4660455392446485
- winner=fep_habit_only; weekly_winner=softmax

### Решения
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

### Неудачи
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3

### Артефакты
- `reports/run_v0.6.0.md`, `run_v0.6.0_full.json`


---

## v0.7.0 — run_experiment (2026-09-03T13:06:31.788853+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.7.0.json`
- Рецепт: softmax_fep_ab

### Holdout
- winner_next=fep_habit_only; winner_weekly=softmax
- comparison={"next_step_accuracy": {"softmax": 0.5503704040358133, "fep_habit_only": 0.5508157978457483, "fep_full_efe": 0.5483797663954916, "fep_0_5_0_crooked": 0.4660455392446485}, "top3_accuracy": {"softmax": 0.911221197109485, "fep_habit_only": 0.9018770167704404, "fep_full_efe": 0.9055856019633687}, "weekly_events_corr": {"softmax": 0.9215900380017684, "fep_habit_only": 0.8611119681301113, "fep_full_efe": 0.8610396814331969, "fep_0_5_0_crooked": 0.8675680432440032}, "cross_entropy": {"softmax": 1.0443371175280967, "fep_habit_only": 1.2496977476252735, "fep_full_efe": 1.358448069756907}, "sim_wall_sec": {"softmax": 8.045155938001699, "fep_habit_only": 6.210717144000228, "fep_full_efe": 10.540984439001477}}

### Решения
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

### Артефакты
- `reports/run_v0.7.0.md`, `run_v0.7.0_full.json`


---

## v0.8.0 — run_experiment (2026-09-03T13:51:25.316960+00:00)

### Изменения
- Единый entrypoint; конфиг: `configs/experiments/v0.8.0.json`
- Рецепт: agent_rules

### Holdout
- winner_next=softmax; winner_weekly=None
- comparison={"next_step_accuracy": {"counts": 0.6243750946826239, "softmax": 0.629450083320709}, "top3_accuracy": {"counts": 0.849871231631571, "softmax": 0.861687623087411}, "cross_entropy": {"counts": 2.2233572535629285, "softmax": 1.2965110799102615}, "n": {"counts": 13202, "softmax": 13202}}

### Решения
- Срез обвязки: FEP / case-head / stress / prune вне критического пути
- Второй организм: HOSPITAL2011, не склеивать с BPIC2012
- Прогон recipe=agent_rules через run_experiment.py (версия 0.8.0)
- package_version=0.8.0
- FEP / case-head / stress top-3 / prune_min_support вне критического пути
- λ не входит в обучение; softmax — только A/B по CE holdout
- Softmax CE holdout лучше счётчиков (1.2965 < 2.2234) — политика = softmax
- Диагностика: агентов=33, незаменимых частых действий (уник. носитель)=61

### Артефакты
- `reports/run_v0.8.0.md`, `run_v0.8.0_full.json`

---

## v0.9.1 — разделение контуров (2026-09-03)

### Изменения
- `run_diagnostic.py` / `run_simulator.py`; `configs/diagnostic/`, `configs/simulator/`
- `docs/CONTOURS.md` — факт / продукт / R&D

### Решения
- Диагност (Hospital v0.8.0) ≠ симулятор (BPIC2012 legacy)
- `run_experiment.py` — legacy с DeprecationWarning

---

## v0.9.0 — BPIC2019 (2026-09-03)

### Изменения
- Третий донор: BPIC2019 (закупки NL), `configs/simulator/v0.9.0.json`
- Ingest: filter с 2018-01-01, subsample 12k+8k, amount=`Cumulative net worth (EUR)`, roles=procurement

### Holdout (subsample 8k кейсов)
| | softmax | fep_habit | fep_full |
|--|---------|-----------|----------|
| next-step | **0.937** | 0.936 | 0.935 |
| top-3 | 0.986 | 0.987 | 0.989 |
| weekly_corr | 0.966 | **0.980** | 0.972 |

### Решения
- На BPIC2019 процесс детерминированнее BPIC2012 (next ~0.94 vs ~0.55)
- FEP не выигрывает next-step; weekly лучше у habit — как на BPIC2012, не KPI продукта
- Wall: parse XES 136s, sim ~10s/рука

### Артефакты
- `reports/simulator/run_v0.9.0.md`, `holdout_metrics_v0.9.0.json`

---

## v0.10.0 — queue_des (2026-09-03)

### Изменения
- `src/orgtwin/sim/queue_des.py`: capacity, FIFO, `input_flow_multiplier`
- `SimConfig.queue_mode`; `engine.simulate_batch` делегирует при `queue_mode=true`
- `scripts/run_queue_stress.py`

### Holdout (BPIC2012, 5658 кейсов)
| поток | max_queue (агент 112) | max_queue_any |
|-------|----------------------|---------------|
| ×1 | 4236 | 4236 |
| ×2 | 9905 | 9905 |

### Решения
- Метрика нагрузки = **длина очереди**, не Σdt / case-head
- Service time = `latency_sec` из fit, без Ridge
- Удалён `run_v0_6_0.py`, кэш `bpic2019_events.pkl`

### Артефакты
- `reports/simulator/run_v0.10.0-queue.md`, `queue_stress_bpic2012.json`
- `docs/SIMULATOR_HONEST.md`, `docs/HISTORY.md`

---

## v0.10.1 — queue stress BPIC2019 (2026-09-03)

### Holdout (8k кейсов, subsample)
| поток | max_queue (NONE) | max_queue_any |
|-------|------------------|---------------|
| ×1 | 4568 | 4568 |
| ×2 | 9150 | 9150 |

### Решения
- `run_queue_stress.py --config` для любого донора
- Починка overflow: cap service time (dt_max), auto horizon, safe timestamps

### Артефакты
- `reports/simulator/queue_stress_bpic2019.json`, `run_v0.10.1-queue-bpic2019.md`

---

## v0.11.0 — full PoC (2026-09-03)

### Holdout BPIC2012
- counts next=0.546 / softmax=0.550; top-3 0.892 / 0.911
- queue ×1 max=4281 (агент 112); ×2 max=9958; ×2+слот1 max=8555

### Решения
- Ghost NONE/UNKNOWN не KPI узкого места
- PoC = диагност + очередь + сценарий найма слота

### Артефакты
- `reports/poc/POC.md`, `poc_v0.11.0.json`

---

## diagnostic 0.8.8–0.8.10 — мутации Information по всем рёбрам (2026-09-03)

### Изменения
- `diagnose_edge_field`: блок `mutation` (доля рёбер/handover, mass, tertile, глобальный топ полей).
- Исключены `org:resource` / `org:group` из кандидатов Information.

### Факт
| Донор | рёбра с мутацией | handover с мутацией |
|---|---|---|
| Sepsis 0.8.8 | 49/144 | 2640/3262 (81%) |
| BPIC2012 0.8.9 | 0/1694 | 0/35448 |
| Hospital 0.8.10 | 184/184 | 8582/8582 |

BPIC кандидаты только `case:REG_DATE`, `case:AMOUNT_REQ`. Hospital 100% тянет `Producer code` (алиас смены группы).

### Артефакты
- `reports/diagnostic/EDGE_CHANGED_FIELDS_COMPARISON.md`
- `run_v0.8.8.md`, `run_v0.8.9.md`, `run_v0.8.10.md`
