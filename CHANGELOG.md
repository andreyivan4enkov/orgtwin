# Changelog

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).  
Версии: [Semantic Versioning](https://semver.org/lang/ru/) — `MAJOR.MINOR.PATCH`.

Каждый прогон эксперимента → отдельный минор/патч + запись в `reports/LAB_JOURNAL.md`.  
**Не правим старые прогоны задним числом** — только новая версия.

---

## [0.4.0] — 2026-09-03

### Added
- Бренд и репозиторий **OrgTwin**; пакет `orgtwin`.
- Semver: `VERSION`, `pyproject.toml`, этот CHANGELOG.
- Батч-подготовка признаков в симуляции (ускорение vs поштучный encode).
- Калибровка длины траектории под case-level duration head (масштабирование dt).
- Стресс-тест: отключение топ-N агентов по нагрузке + метрики каскада.
- Пайплайн `scripts/run_v0_4_0.py`, артефакты `reports/run_v0.4.0.*`.

### Changed
- Имя пакета `b2b_sim` → `orgtwin`.

### Fixed
- (наследует) векторизация Action-имён вместо `DataFrame.apply`.

---

## [0.3.0] — 2026-09-03

### Added
- Softmax-политики + Ridge(log1p(dt)) + case-level duration head.
- `ExperimentConfig` / константы, LAB_JOURNAL, failures JSON.
- Пайплайны исторически: `run_pipeline_v1.py`, `run_pipeline_v2.py` (архив логики → 0.2 / 0.3).

### Failed / documented
- Эмерджентная сумма dt: Spearman ≈ 0.
- max_steps=80 aborted (wall-time).
- weekly_corr регрессия 0.95 → 0.87 при saga (не закрыто A/B).

---

## [0.2.0] — 2026-09-03

### Added
- Multinomial logistic (softmax) P(Action|Information, agent).
- Membrane mask + prune min_support=30.
- Holdout next-step accuracy / top-3.

---

## [0.1.0] — 2026-09-03

### Added
- Донор BPIC2012, IR Information/Action, эмпирические счётчики, первый fit/holdout.
- Выявлено: weekly_corr отрицательная из-за относительного времени сима.
