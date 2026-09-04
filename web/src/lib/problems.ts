import type { Agent, OrgModel, QueueSlice } from "../lib/api";
import { agentTitle, roleTitle, roleWhat } from "../lib/orgLabels";

export type ProblemKind = "queue" | "stuck" | "exclusive" | "excluded";

export interface ProblemExplain {
  kind: ProblemKind;
  title: string;
  meaning: string;
  blocks: string;
  actions: string[];
  severity: "warn" | "danger" | "info";
}

export function explainAgentProblem(
  model: OrgModel,
  agent: Agent,
  queueSlice?: QueueSlice | null
): ProblemExplain | null {
  const q = queueSlice?.top_agents.find((t) => t.id === agent.id);
  const isBottleneck = queueSlice?.bottleneck_agent === agent.id;
  const pressure =
    q && queueSlice
      ? q.max_queue / Math.max(queueSlice.max_queue_any_real, 1)
      : 0;
  const stuck = agent.stuck_frac ?? 0;

  if (isBottleneck || pressure >= 0.75) {
    return {
      kind: "queue",
      title: "Узкое место: очередь",
      severity: "danger",
      meaning: `${agentTitle(agent.id, model.donor_id)} — самое загруженное звено в текущем срезе нагрузки. Макс. очередь: ${
        q?.max_queue ?? queueSlice?.max_queue_any_real ?? "—"
      }.`,
      blocks:
        "Дела скапливаются перед этим сотрудником: следующие шаги процесса ждут свободный слот. Растёт время ожидания по всей цепочке.",
      actions: [
        "Добавить слот занятости этому сотруднику (сценарий ×2 + слот).",
        "Проверить «что если» — вычеркнуть сотрудника и посмотреть, куда уйдёт нагрузка.",
        "Снизить входящий поток только у его подразделения (локальная нагрузка).",
        "Посмотреть покрывало: кто передаёт ему дела и можно ли разгрузить вход.",
      ],
    };
  }
  if (pressure >= 0.4) {
    return {
      kind: "queue",
      title: "Повышенная очередь",
      severity: "warn",
      meaning: `У ${agentTitle(agent.id, model.donor_id)} очередь заметно выше средней (до ${q?.max_queue ?? "—"}).`,
      blocks: "Риск затора при росте потока. Пока не критично, но уже сигнал.",
      actions: [
        "Сравнить срезы ×1 и ×2 в режиме «Поток».",
        "Усилить слот или перераспределить передачи на коллег.",
      ],
    };
  }
  if (stuck >= 0.35) {
    return {
      kind: "stuck",
      title: "Застревание в действиях",
      severity: "danger",
      meaning: `${agentTitle(agent.id, model.donor_id)} в ${(stuck * 100).toFixed(0)}% событий «зациклен» на однотипных шагах.`,
      blocks:
        "Процесс не продвигается: повтор одних и тех же действий без перехода дальше. Похоже на локальный минимум поведения.",
      actions: [
        "Открыть локальные правила справа — какое действие доминирует.",
        "Проверить незаменимые действия: если шаг умеет только он — это риск.",
        "В сценарии «что если» убрать сотрудника и увидеть, ломается ли поток.",
      ],
    };
  }
  if (stuck >= 0.15) {
    return {
      kind: "stuck",
      title: "Умеренное застревание",
      severity: "warn",
      meaning: `Застревание ${(stuck * 100).toFixed(0)}% у ${agentTitle(agent.id, model.donor_id)}.`,
      blocks: "Часть кейсов буксует, но не весь поток.",
      actions: ["Смотреть правила входа→действия", "Сравнить с коллегами подразделения"],
    };
  }
  if (agent.exclusive_actions.length > 0) {
    const top = agent.exclusive_actions[0];
    return {
      kind: "exclusive",
      title: "Незаменимый исполнитель",
      severity: "warn",
      meaning: `${agentTitle(agent.id, model.donor_id)} почти один делает «${top.action}» (${(
        top.share * 100
      ).toFixed(0)}%).`,
      blocks: "Если его убрать — эти шаги некому выполнять без переобучения/переназначения.",
      actions: [
        "Сценарий «без сотрудника» — проверить падение системы.",
        "Заложить дублёра в режиме «Проект».",
      ],
    };
  }
  return null;
}

export function explainRoleProblem(
  model: OrgModel,
  roleId: string,
  queueSlice?: QueueSlice | null
): ProblemExplain | null {
  const agents = model.agents.filter((a) => a.role_id === roleId);
  const hot = agents
    .map((a) => ({ a, e: explainAgentProblem(model, a, queueSlice) }))
    .filter((x) => x.e && x.e.severity !== "info");
  if (hot.length === 0) return null;
  const danger = hot.filter((x) => x.e!.severity === "danger");
  return {
    kind: "queue",
    title: danger.length ? "Подразделение под ударом" : "Напряжение в подразделении",
    severity: danger.length ? "danger" : "warn",
    meaning: `${roleTitle(roleId, model.donor_id)}: ${roleWhat(roleId, model.donor_id)}. Проблемных сотрудников: ${hot.length}.`,
    blocks: danger.length
      ? "В отделе есть критичные заторы или застревания — отдел тянет соседние."
      : "Есть предупреждения по людям отдела.",
    actions: [
      "Кликнуть красного сотрудника — детали.",
      "Вычеркнуть всё подразделение в сценарии «что если».",
      "Поднять нагрузку только на этот отдел (не на всю компанию).",
    ],
  };
}
