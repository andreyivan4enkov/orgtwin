# OrgTwin v0.4.0

## Суть релиза
- Батч-encode softmax/timing в симуляции
- Калибровка длительности кейса под case-head (явный костыль)
- Стресс: выключение топ-3 агентов по fit-нагрузке
- Версионирование semver; артефакты только `*v0.4.0*`

## Результаты прогонов
```json
{
  "baseline_raw": {
    "wall_sec": 10.433176411999739,
    "next_acc": 0.5503704040358133,
    "top3": 0.911221197109485,
    "weekly_corr": 0.9215900380017684,
    "dur_spearman": 0.002365111923376657,
    "sim_events": 86234,
    "hit_max": 760
  },
  "calibrated": {
    "wall_sec": 11.018476180997823,
    "next_acc": 0.5503704040358133,
    "top3": 0.911221197109485,
    "weekly_corr": 0.8573853156611383,
    "dur_spearman": 0.22446562987699406,
    "sim_events": 86234,
    "hit_max": 760
  },
  "stress_top3_calibrated": {
    "wall_sec": 13.44012197399934,
    "next_acc": 0.5503704040358133,
    "top3": 0.911221197109485,
    "weekly_corr": 0.8419775498757414,
    "dur_spearman": 0.21967442231721024,
    "sim_events": 107006,
    "hit_max": 1262
  }
}
```

## Stress delta
```json
{
  "sim_events_delta": 20772,
  "weekly_corr_stress": 0.8419775498757414,
  "dur_spearman_stress": 0.21967442231721024,
  "hit_max_stress": 1262,
  "hit_max_base": 760
}
```

## Решения
- Релиз OrgTwin 0.4.0: батч-encode, калибровка dt→case-head, stress top-3 агентов
- Старые run_v0/v1/v2 не перезаписываем
- solver=saga (A/B lbfgs отложен на 0.4.1)
- Откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- Стресс stress_top3_calibrated: disabled=['112', 'UNKNOWN', '11189']
- Калибровка подняла duration Spearman до 0.224 (не эмерджентность — зафиксировано)
- Батч-сима baseline_raw wall=10.4s
- Стресс delta: {'sim_events_delta': 20772, 'weekly_corr_stress': 0.8419775498757414, 'dur_spearman_stress': 0.21967442231721024, 'hit_max_stress': 1262, 'hit_max_base': 760}

## Неудачи / риски
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
- **PRUNE_DECLINED_ROLLED_BACK**: Восстановлены на мембране: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE'] (риск PRUNE_MAY_BIAS_TERMINALS из 0.3.0)
