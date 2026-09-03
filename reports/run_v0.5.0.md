# OrgTwin v0.5.0

## Суть релиза
A/B на одном доноре BPIC2012 / одном split:
- **softmax** — мультиномиальная логистика P(Action|Information, agent)
- **fep_efe** — активный вывод Friston: G = Risk + Ambiguity − Habit, π∝exp(−γG)

## Сравнение (holdout, raw sim)
| Метрика | Softmax | FEP/EFE | Δ (FEP−SM) |
|---------|---------|---------|------------|
| next-step acc | 0.5504 | 0.4660 | -0.0843 |
| top-3 | 0.9112 | 0.8465 | -0.0647 |
| CE (nats) | 1.0443 | 1.7636 | +0.7193 |
| weekly_corr | 0.9215900380017684 | 0.8675680432440032 | -0.05402199475776526 |
| dur Spearman raw | 0.002365111923376657 | 0.01061050689940539 | — |
| wall sec | 9.0 | 10.3 | — |

Победитель next-step: **softmax**; weekly: **softmax**.

## Свободная энергия
```json
{
  "softmax_proxy_CE_plus_lamH": 1.0949036017340623,
  "fep_variational_FE_gen_CE": 1.7636194276200061,
  "fep_mean_G_truth": 3.49081637266933,
  "note": "Метрики FE несопоставимы 1:1: у softmax — CE+λH прокси; у FEP — generative CE / EFE"
}
```

## Решения
- Релиз OrgTwin 0.5.0: A/B Softmax vs FEP (EFE Friston)
- Один split 3+2, один seed; timing обучается на softmax-бандле edges, FEP шарит edges
- Калибровка длительности — для справки; сравнение политик по raw next-step и weekly
- Softmax: откат прунинга DECLINED: ['APPLICATION:O_DECLINED|COMPLETE', 'OFFER:O_DECLINED|COMPLETE']
- FEP cfg: α=0.5 γ=2.0 w_r/a/h=1.0/1.0/1.0
- Победитель next-step accuracy: softmax
- Победитель weekly_corr: softmax

## Неудачи / риски
- **SPLIT_NOT_7_3**: split 3+2, цель 7+3
