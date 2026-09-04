# Проверка directed edge field

Сравнение на трёх донорах. Рёбра считаются только по соседним сменам агента внутри кейса.  
Каждое `A→B` — отдельный directed edge; `B→A` не симметризуется.

## Сводка

| Донор | Агенты | Рёбра | Возможные | Плотность | mean H_out |
|---|---:|---:|---:|---:|---:|
| Hospital 2011 | 33 | 184 | 1056 | 0.1742 | 1.0810 |
| Sepsis 2016 | 25 | 144 | 600 | 0.2400 | 1.2048 |
| BPIC2012 | 65 | 1694 | 4160 | 0.4072 | 3.1963 |

`mean H_out` = средняя энтропия исходящего маршрута агента в битах.

## Характер поля

- **Sepsis**: поле компактное, маршруты узкие, top-рёбра клинически понятны (`A→C`, `C→A`, `B→E`). Это лучший донор для проверки идеи «смысл на ребре».
- **Hospital**: поле разреженнее, но крупные лабораторные и nursing-узлы формируют явные асимметричные каналы (`Nursing ward → General Lab Clinical Chemistry`, `Medical Microbiology → General Lab Clinical Chemistry`).
- **BPIC2012**: поле заметно шире и шумнее; много агентов, высокая плотность и высокая средняя энтропия маршрутов. Это лучше для стресс-теста алгоритма, но хуже для интуитивной читаемости.

## Примеры сильных рёбер

### Hospital 2011

- `Nursing ward → General Lab Clinical Chemistry`: `n=1144`, `Pout=0.5652`, `Pin=0.4460`
- `Medical Microbiology → General Lab Clinical Chemistry`: `n=435`, `Pout=0.9932`, `Pin=0.1696`
- `Internal Specialisms clinic → Nursing ward`: `n=377`, `Pout=0.6379`, `Pin=0.1836`

### Sepsis 2016

- `A → C`: `n=438`, `Pout=0.4011`, `Pin=0.8975`
- `C → A`: `n=392`, `Pout=0.8000`, `Pin=0.5513`
- `B → E`: `n=288`, `Pout=0.3318`, `Pin=0.7956`
- `E → ?`: `n=151`, `Pout=0.9869`, `Pin=0.9934`

### BPIC2012

- `112 → UNKNOWN`: `n=1214`, `Pout=0.2184`, `Pin=0.1814`
- `112 → 11189`: `n=449`, `Pout=0.0808`, `Pin=0.3046`
- `11029 → UNKNOWN`: `n=368`, `Pout=1.0000`, `Pin=0.0550`

## Вывод

- Для **полноценного теста самой методики directed edge field** текущих данных достаточно.
- Для **наиболее ясной демонстрации** лучше всего уже подходят `Sepsis` и `Hospital`.
- Для **приближения к Bitrix24-сценарию** по типу hand-over/route complexity полезен `BPIC2012`; ещё лучше будет отдельный helpdesk / incident donor, но это уже не обязательный блокер.

Артефакты:

- `data/derived/diagnostic/edge_field_v0.8.0.json`
- `data/derived/diagnostic/edge_field_v0.8.1.json`
- `data/derived/diagnostic/edge_field_v0.8.2.json`
- `reports/diagnostic/run_v0.8.0.md`
- `reports/diagnostic/run_v0.8.1.md`
- `reports/diagnostic/run_v0.8.2.md`
