/**
 * Паттерны BI / process mining, которые применяем в OrgTwin.
 *
 * Celonis PI Social / Network Explorer, pm4py org (handover), Power BI org/decomposition:
 * 1) Иерархия и сеть — РАЗНЫЕ виды, не смешивать на одном холсте.
 * 2) Иерархия = вертикальное дерево / колонки подразделений (кто где сидит).
 * 3) Сеть передач = handover; полное SNA перегружает → по умолчанию
 *    эго-окрестность выбранного узла (марковское покрывало по рёбрам передачи).
 * 4) Progressive disclosure: детали в карточке справа, на сцене — только ответ на один вопрос.
 * 5) У каждой сцены одна фраза «на какой вопрос отвечает».
 */

export type StructureView = "hierarchy" | "blanket";

export const STRUCTURE_VIEWS: {
  id: StructureView;
  label: string;
  question: string;
  how: string;
}[] = [
  {
    id: "hierarchy",
    label: "Иерархия",
    question: "Как устроена компания: организация → подразделения → сотрудники?",
    how: "Как org chart в Power BI / HR: колонки отделов, внутри люди. Без стрелок передачи дел.",
  },
  {
    id: "blanket",
    label: "Покрывало",
    question: "С кем связан выбранный сотрудник в работе (кто отдаёт / кому передаёт / коллеги)?",
    how: "Как локальный срез Celonis Social / handover в pm4py: только окрестность узла, не весь граф.",
  },
];
