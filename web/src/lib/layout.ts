import type { OrgModel, QueueSlice } from "./api";
import { tokens } from "./tokens";

export type SliceKey = "x1" | "x2" | "x2_plus1";

export type LayoutBox = { id: string; x: number; y: number; w: number; h: number };

/** Простая проверка пересечений (с запасом padding). */
export function hasCollisions(boxes: LayoutBox[], pad = 8): boolean {
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      if (
        a.x - pad < b.x + b.w + pad &&
        a.x + a.w + pad > b.x - pad &&
        a.y - pad < b.y + b.h + pad &&
        a.y + a.h + pad > b.y - pad
      ) {
        return true;
      }
    }
  }
  return false;
}

export function queuePressureMap(
  slice: QueueSlice | null | undefined
): Map<string, number> {
  const m = new Map<string, number>();
  if (!slice) return m;
  const max = Math.max(...(slice.top_agents || []).map((a) => a.max_queue), 1);
  for (const a of slice.top_agents || []) {
    m.set(a.id, a.max_queue / max);
  }
  if (slice.bottleneck_agent) {
    m.set(slice.bottleneck_agent, Math.max(m.get(slice.bottleneck_agent) || 0, 1));
  }
  return m;
}

export function congestionStroke(
  stuck: number | null | undefined,
  pressure: number | undefined
): string {
  const p = pressure ?? 0;
  if (p >= 0.75) return tokens.colors.danger;
  if (p >= 0.4) return tokens.colors.warn;
  if (stuck != null && stuck >= 0.35) return tokens.colors.danger;
  if (stuck != null && stuck >= 0.15) return tokens.colors.warn;
  return tokens.colors.accent;
}

export function agentSize(n: number, maxN: number): number {
  const t = maxN > 0 ? n / maxN : 0;
  return Math.round(34 + t * 22); // 34…56
}

/**
 * Иерархический layout без пересечений:
 * орг → ряд ролей с широкими колонками → сетка агентов под каждой ролью.
 */
export function layoutOrgTree(model: OrgModel, maxRoles = 8, maxAgentsPerRole = 6): {
  positions: Record<string, { x: number; y: number }>;
  sizes: Record<string, { w: number; h: number }>;
  visibleAgents: typeof model.agents;
  visibleRoles: typeof model.roles;
  boxes: LayoutBox[];
} {
  const roles = model.roles.slice(0, maxRoles);
  const roleIds = new Set(roles.map((r) => r.id));
  const agentsAll = model.agents
    .filter((a) => roleIds.has(a.role_id))
    .sort((a, b) => b.n_events - a.n_events);
  const maxN = Math.max(...agentsAll.map((a) => a.n_events), 1);

  const byRole: Record<string, typeof agentsAll> = {};
  for (const a of agentsAll) {
    const list = (byRole[a.role_id] ||= []);
    if (list.length < maxAgentsPerRole) list.push(a);
  }
  const visibleAgents = roles.flatMap((r) => byRole[r.id] || []);

  const AGENT_STEP_X = 88;
  const AGENT_STEP_Y = 88;
  const ROLE_H = 72;
  const COL_GAP = 56;
  const TOP = 24;
  const ROLE_Y = 120;
  const AGENT_TOP = ROLE_Y + ROLE_H + 56;

  const colWidths: number[] = roles.map((r) => {
    const n = (byRole[r.id] || []).length;
    const cols = Math.min(3, Math.max(1, n));
    return Math.max(200, cols * AGENT_STEP_X + 40);
  });

  let xCursor = 40;
  const roleX: number[] = [];
  for (let i = 0; i < roles.length; i++) {
    roleX.push(xCursor);
    xCursor += colWidths[i] + COL_GAP;
  }
  const totalW = Math.max(xCursor - COL_GAP, 480);
  const orgW = 260;

  const positions: Record<string, { x: number; y: number }> = {
    org: { x: totalW / 2 - orgW / 2, y: TOP },
  };
  const sizes: Record<string, { w: number; h: number }> = {
    org: { w: orgW, h: 56 },
  };
  const boxes: LayoutBox[] = [
    { id: "org", x: positions.org.x, y: positions.org.y, w: orgW, h: 56 },
  ];

  roles.forEach((r, i) => {
    const w = Math.min(colWidths[i] - 12, 220);
    const x = roleX[i] + (colWidths[i] - w) / 2;
    const id = `role:${r.id}`;
    positions[id] = { x, y: ROLE_Y };
    sizes[id] = { w, h: ROLE_H };
    boxes.push({ id, x, y: ROLE_Y, w, h: ROLE_H });

    const list = byRole[r.id] || [];
    const cols = Math.min(3, Math.max(1, list.length));
    list.forEach((a, j) => {
      const col = j % cols;
      const row = Math.floor(j / cols);
      const size = agentSize(a.n_events, maxN);
      const ax =
        roleX[i] +
        (colWidths[i] - cols * AGENT_STEP_X) / 2 +
        col * AGENT_STEP_X +
        (AGENT_STEP_X - size) / 2;
      const ay = AGENT_TOP + row * AGENT_STEP_Y;
      positions[a.id] = { x: ax, y: ay };
      sizes[a.id] = { w: size, h: size };
      boxes.push({ id: a.id, x: ax, y: ay, w: size, h: size });
    });
  });

  return { positions, sizes, visibleAgents, visibleRoles: roles, boxes };
}

/** Сетка агентов для режима потока — без наложений. */
export function layoutFlowGrid(
  model: OrgModel,
  maxAgents = 18
): {
  positions: Record<string, { x: number; y: number }>;
  boxes: LayoutBox[];
  agents: typeof model.agents;
} {
  const agents = [...model.agents].sort((a, b) => b.n_events - a.n_events).slice(0, maxAgents);
  const STEP = 140;
  const SIZE = 44;
  const COLS = 6;
  const positions: Record<string, { x: number; y: number }> = {};
  const boxes: LayoutBox[] = [];
  agents.forEach((a, i) => {
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    const x = 48 + col * STEP;
    const y = 72 + row * STEP;
    positions[a.id] = { x, y };
    boxes.push({ id: a.id, x, y, w: SIZE, h: SIZE });
  });
  return { positions, boxes, agents };
}

/**
 * Поток + нагрузка: приоритет узких мест и связанных по handover,
 * раскладка слева→направо (кто отдаёт → кто принимает).
 */
export function layoutFlowLoad(
  model: OrgModel,
  queueSlice?: QueueSlice | null,
  maxAgents = 22
): {
  positions: Record<string, { x: number; y: number }>;
  boxes: LayoutBox[];
  agents: typeof model.agents;
} {
  const byId = Object.fromEntries(model.agents.map((a) => [a.id, a]));
  const picked = new Map<string, (typeof model.agents)[0]>();

  const take = (id: string | null | undefined) => {
    if (!id || !byId[id] || picked.has(id)) return;
    picked.set(id, byId[id]);
  };

  take(queueSlice?.bottleneck_agent);
  for (const r of queueSlice?.top_agents || []) take(r.id);

  const byEvents = [...model.agents].sort((a, b) => b.n_events - a.n_events);
  for (const a of byEvents) {
    if (picked.size >= maxAgents) break;
    take(a.id);
  }

  // добрать соседей по рёбрам к уже выбранным
  const seed = [...picked.keys()];
  for (const e of model.edges) {
    if (picked.size >= maxAgents) break;
    if (seed.includes(e.from_agent)) take(e.to_agent);
    if (seed.includes(e.to_agent)) take(e.from_agent);
  }

  const agents = [...picked.values()];
  const ids = new Set(agents.map((a) => a.id));

  const net = new Map<string, number>();
  for (const id of ids) net.set(id, 0);
  for (const e of model.edges) {
    if (!ids.has(e.from_agent) || !ids.has(e.to_agent)) continue;
    net.set(e.from_agent, (net.get(e.from_agent) || 0) + e.weight);
    net.set(e.to_agent, (net.get(e.to_agent) || 0) - e.weight);
  }

  const sorted = [...agents].sort(
    (a, b) => (net.get(b.id) || 0) - (net.get(a.id) || 0) || b.n_events - a.n_events
  );
  const STEP_X = 170;
  const STEP_Y = 120;
  const SIZE = 48;
  const positions: Record<string, { x: number; y: number }> = {};
  const boxes: LayoutBox[] = [];

  // выровнять: сильнее «источники» слева
  const byNetCols = [[], [], [], [], []] as (typeof agents)[];
  for (const a of sorted) {
    const s = net.get(a.id) || 0;
    const col = s > 0.15 ? 0 : s > 0.05 ? 1 : s > -0.05 ? 2 : s > -0.15 ? 3 : 4;
    byNetCols[col].push(a);
  }
  // если колонка пуста — не страшно
  byNetCols.forEach((colAgents, col) => {
    colAgents
      .sort((a, b) => {
        const qa = queueSlice?.top_agents.find((t) => t.id === a.id)?.max_queue ?? 0;
        const qb = queueSlice?.top_agents.find((t) => t.id === b.id)?.max_queue ?? 0;
        return qb - qa || b.n_events - a.n_events;
      })
      .forEach((a, row) => {
        const x = 56 + col * STEP_X;
        const y = 80 + row * STEP_Y;
        positions[a.id] = { x, y };
        boxes.push({ id: a.id, x, y, w: SIZE, h: SIZE });
      });
  });

  return { positions, boxes, agents: agents.filter((a) => positions[a.id]) };
}

