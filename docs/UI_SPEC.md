# OrgTwin — спецификация веб-интерфейса

Самохостируемый UI: аудит лога + проектирование оргструктуры + срезы нагрузки.
Источник истины по продукту: контуры в [CONTOURS.md](CONTOURS.md); честность симулятора — [SIMULATOR_HONEST.md](SIMULATOR_HONEST.md).

## Цель

Открыл на своём сервере → выбрал донор → видит структуру, роли, сотрудников-нейроавтоматов с локальными правилами → смотрит поток кейсов → гоняет срезы ×1 / ×2 / слот+1. Режим **Проект** — ручная правка или greenfield.

## UX

- Одна задача на экран: Аудит | Поток | Нагрузка | Проект.
- Слева rail (~21%), центр stage, справа inspect (~34%).
- Срезы — сегмент-контроль, не формы из 20 полей.
- Анимация только для потока кейсов и роста очереди.
- Подписи «из лога» vs «допущение»; ghost `NONE`/`UNKNOWN` не KPI.

## Дизайн-токены

Файл: [`web/src/styles/design-tokens.css`](../web/src/styles/design-tokens.css).

### φ-сетка

| Токен | px |
|-------|-----|
| space-1…6 | 8, 13, 21, 34, 55, 89 |
| rail / inspect | 21% / 34% |
| type | 13 / 21 / 34 / 55 |

### Палитра

| Токен | Hex |
|-------|-----|
| bg | `#F7F6F3` |
| surface | `#FFFFFF` |
| ink | `#1C1B19` |
| ink-muted | `#6B6860` |
| line | `#E4E1D9` |
| accent | `#0F6E56` |
| warn | `#B54708` |
| danger | `#A32D2D` |
| info | `#2F5D8A` |

Шрифты: IBM Plex Sans + IBM Plex Mono.

### Сигнатуры сущностей

| Тип | Форма |
|-----|--------|
| org | широкий rect со срезом |
| role | rounded rect |
| agent | круг (+ квадрат слота) |
| action | ромб |
| case | вертикальный «лист» |
| queue | штрихи warn |
| manual | пунктир warn |

## OrgModel (JSON)

```text
donor_id, origin: log|manual|hybrid
roles[], agents[], rules[], edges[]
metrics?, queue_slices?, flow_sample?
```

API: `GET /api/donors`, `GET /api/org-model/{id}`, `POST /api/queue-stress/{id}`, `GET/PUT /api/design/{id}`.

## Стек

FastAPI (`apps/api`) + Vite/React (`web`) + React Flow + docker-compose.

## Вне v1

Живые коннекторы SAP/1С/Битрикс; SSO; mobile-first; полный BPMN.
