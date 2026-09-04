# Сводка мутаций Information по всем directed рёбрам

Контекст: предыдущий срез смотрел только `top_edges` (частотные hand-over). BPIC там выглядел «пустым». Теперь `diagnose_edge_field` считает агрегаты **по всем ненулевым рёбрам**: доля рёбер/handover с мутацией, `mutation_mass = avg_n × n`, tertile по `handover_count`.

Код: `src/orgtwin/diag/edge_field.py` (`mutation` в возврате). В отчёт: секция «Мутации Information на всех рёбрах».

Прогоны:
- Sepsis: `configs/diagnostic/v0.8.8.json` → `reports/diagnostic/run_v0.8.8.md`
- BPIC2012: `configs/diagnostic/v0.8.9.json` → `reports/diagnostic/run_v0.8.9.md`
- Hospital 2011: `configs/diagnostic/v0.8.10.json` → `reports/diagnostic/run_v0.8.10.md`

## Сводка

| Донор | Кандидатов полей | Рёбер с мутацией | Handover с мутацией | Взвеш. avg_n полей | Где сидят мутации |
|---|---|---|---|---|---|
| Sepsis | 27 | 49 / 144 (34%) | 2640 / 3262 (**81%**) | 8.69 | tertile **high**: 71% рёбер; low: 10% |
| Hospital | 123 | **184 / 184 (100%)** | **8582 / 8582 (100%)** | 3.67 | все tertile = 100% |
| BPIC2012 | **2** | **0 / 1694 (0%)** | **0 / 35448 (0%)** | 0 | ни на редких, ни на частых |

Кандидаты BPIC: только `case:REG_DATE`, `case:AMOUNT_REQ` — атрибуты кейса, между соседними событиями не меняются.

## Что получилось

**Sepsis — механика видна и концентрируется на трафике.**  
Не 73% «топ-15», а факт по полному графу: треть рёбер несёт мутации, но это **81% всех hand-over**. Топ mass: `A→C` / `C→A` с avg_n ≈ 23.7 (`InfectionSuspected` и пакет диагностических флагов). Лабораторные рёбра (`A→B`, `B→A`, `B→E`) меняют 1–2 поля (`Leucocytes`, `LacticAcid`, `CRP`). Редкие рёбра чаще «пустые» по Information.

**Hospital — мутация на каждом hand-over, но это не чистая клиника.**  
Глобальный топ: `Producer code` (8582 = все handover), `Activity code` (8201), `Specialism code` (7674), `Section` (6921). Это коды процесса/лаборатории, которые почти всегда переписываются вместе со сменой `org:group`. Клинический смысл есть, но 100% — ещё и «алиас агента/действия», не только содержимое кейса.

**BPIC2012 — пустота не артефакт top-среза.**  
0 из 1694 рёбер, 0 из 35448 hand-over, все три tertile нулевые. В логе почти нет event-level Information: сумма заявки и дата регистрации кейса статичны. Смысл hand-over здесь в **Action / lifecycle** (`W_… START/COMPLETE`), не в смене полей. Entity-layer это уже показывал (`information_field`: 6 штук).

## Что не получилось / ограничение метода

1. Сравнение «changed columns as-is» не отличает клинический факт от кода, который 1:1 следует за агентом (`Producer code`).
2. Case-level поля (BPIC `AMOUNT_REQ`) никогда не дадут мутации на ребре `i→i+1`.
3. Action намеренно исключён из кандидатов (`concept:name`, `lifecycle:transition`) — для BPIC это как раз носитель динамики.

## Что с этим делать

1. **Продукт (Битрикс / операционный лог):** ждать event-level поля (`UF_*`, статус, сумма на шаге, комментарий, файл). Тогда картина ближе к Sepsis, не к BPIC2012.
2. **Фильтр «алиасов»:** не считать Information поле, которое меняется на ≥95% всех hand-over (Hospital `Producer code`). Оставить как метку мембраны, не как содержимое покрывала.
3. **BPIC как контроль нуля:** лог без event-Information → 0 мутаций на ребре. Если на клиентском логе получится 0 при живых UF — это баг ingest, не «так у бизнеса».
4. **Следующий слой (по желанию):** мутация Action на том же ребре (`prev_action → next_action`) уже есть в `top_action_pairs`; для кредитного лога это основной носитель, для медлога — дополнение к полям.

## Артефакты

- `reports/diagnostic/run_v0.8.8.md`, `run_v0.8.8_full.json`
- `reports/diagnostic/run_v0.8.9.md`, `run_v0.8.9_full.json`
- `reports/diagnostic/run_v0.8.10.md`, `run_v0.8.10_full.json`
- derived: `data/derived/diagnostic/edge_field_v0.8.{8,9,10}.json` (полный список рёбер + блок `mutation`)
