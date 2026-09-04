# Проверка entity-edge layer

Проверка общего слоя сущностей на трёх донорах.  
Сущности: `agent`, `action`, `information_field`, `membrane`.  
Рёбра: `agent_to_action`, `agent_to_agent`, `action_to_action`, `membrane_to_action`, `membrane_to_information_field`.

## Сводка

| Донор | Сущности | Рёбра | agent | action | info_field | membrane |
|---|---:|---:|---:|---:|---:|---:|
| Hospital 2011 | 596 | 4793 | 33 | 420 | 128 | 15 |
| Sepsis 2016 | 98 | 506 | 25 | 16 | 32 | 25 |
| BPIC2012 | 110 | 3129 | 65 | 36 | 6 | 3 |

## Типы рёбер

### Hospital 2011

- `agent_to_action`: 487
- `membrane_to_action`: 453
- `membrane_to_information_field`: 1186
- `action_to_action`: 2483
- `agent_to_agent`: 184

### Sepsis 2016

- `agent_to_action`: 40
- `membrane_to_action`: 40
- `membrane_to_information_field`: 180
- `action_to_action`: 102
- `agent_to_agent`: 144

### BPIC2012

- `agent_to_action`: 1178
- `membrane_to_action`: 64
- `membrane_to_information_field`: 18
- `action_to_action`: 175
- `agent_to_agent`: 1694

## Что видно по донорам

- **Hospital** даёт самый толстый слой `action` и `information_field`: это хороший стресс-тест для многосущностной модели, но он менее нагляден.
- **Sepsis** даёт самый чистый и читаемый каркас: мало действий, много осмысленных `agent↔agent` переходов, отдельные мембраны почти совпадают с агентами.
- **BPIC2012** даёт самый сильный слой `agent_to_agent` и `agent_to_action`: хороший прокси для операционного бизнеса и hand-over между сотрудниками.

## Топ-рёбра по типам

### Hospital 2011

- `action_to_action`: `aanname laboratoriumonderzoek|complete → aanname laboratoriumonderzoek|complete`, `n=2366`, `p=0.5410`
- `agent_to_action`: `General Lab Clinical Chemistry → aanname laboratoriumonderzoek|complete`, `n=4048`, `p=0.1505`
- `agent_to_agent`: `Nursing ward → General Lab Clinical Chemistry`, `n=1144`, `p=0.5652`

### Sepsis 2016

- `action_to_action`: `Leucocytes|complete → CRP|complete`, `n=795`, `p=0.5268`
- `agent_to_action`: `B → Leucocytes|complete`, `n=1530`, `p=0.4203`
- `agent_to_agent`: `A → C`, `n=438`, `p=0.4011`

### BPIC2012

- `action_to_action`: `W_Nabellen offertes|COMPLETE → W_Nabellen offertes|START`, `n=10651`, `p=0.8060`
- `agent_to_action`: `112 → A_PARTLYSUBMITTED|COMPLETE`, `n=7427`, `p=0.2849`
- `agent_to_agent`: `112 → UNKNOWN`, `n=1214`, `p=0.2184`

## Вывод

- Для вашей нелинейной схемы текущих данных уже хватает не только на `agent→agent`, но и на **общий слой сущностей**.
- Следующий логичный шаг — не новый датасет, а **углубление semantics на ребре**: какие поля Information действительно меняются перед `agent→agent` и `action→action`.
- Если позже брать ещё один открытый донор, то лучше helpdesk / incident log: он добавит слой задач и hand-over, близкий к будущему Bitrix24, но сейчас это не блокер.

Артефакты:

- `data/derived/diagnostic/entity_field_v0.8.0.json`
- `data/derived/diagnostic/entity_field_v0.8.1.json`
- `data/derived/diagnostic/entity_field_v0.8.2.json`
