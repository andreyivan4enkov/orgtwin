import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  MarkerType,
  Panel,
  type Node,
  type Edge,
  type ReactFlowInstance,
} from "@xyflow/react";
import type { OrgModel } from "../lib/api";
import { tokens } from "../lib/tokens";
import { congestionStroke } from "../lib/layout";
import { agentShort, agentTitle, agentWhat, roleTitle } from "../lib/orgLabels";
import { useTheme } from "../lib/theme";
import { nodeTypes } from "./EntityNodes";

type Link = {
  id: string;
  weight: number;
  n_events?: number;
  stuck?: number | null;
  role?: string;
  est_handovers?: number;
};

type Nb = {
  parents: Link[];
  children: Link[];
  peers: Link[];
  inMass: number;
  outMass: number;
};

function pressureSig(pressure: Map<string, number>): string {
  if (!pressure.size) return "";
  const parts: string[] = [];
  pressure.forEach((v, k) => {
    parts.push(`${k}:${v.toFixed(2)}`);
  });
  return parts.join("|");
}

/** Марковское покрывало: окрестность + детальная панель связей. */
export function MarkovBlanket({
  model,
  focusId,
  onSelect,
  pressure,
}: {
  model: OrgModel;
  focusId: string;
  onSelect: (id: string) => void;
  pressure: Map<string, number>;
}) {
  const { theme } = useTheme();
  const pSig = useMemo(() => pressureSig(pressure), [pressure]);
  const nb = useMemo(() => neighborhood(model, focusId), [model, focusId]);
  const built = useMemo(
    () => buildBlanket(model, focusId, nb, pressure),
    // pressure читаем при смене pSig / theme; ссылка Map может меняться зря
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [model, focusId, nb, pSig, theme]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(built.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(built.edges);
  const focusRef = useRef(focusId);
  const rfRef = useRef<ReactFlowInstance | null>(null);
  const builtRef = useRef(built);
  builtRef.current = built;

  useEffect(() => {
    const next = builtRef.current;
    const focusChanged = focusRef.current !== focusId;
    focusRef.current = focusId;
    if (focusChanged) {
      setNodes(next.nodes);
      setEdges(next.edges);
      const id = requestAnimationFrame(() => {
        rfRef.current?.fitView({ padding: 0.2, duration: 0 });
      });
      return () => cancelAnimationFrame(id);
    }
    // смена давления/темы — только data, позиции сохраняем
    setNodes((prev) => mergeNodeData(prev, next.nodes));
    setEdges(next.edges);
  }, [focusId, built, setNodes, setEdges]);

  const focus = model.agents.find((a) => a.id === focusId);
  const focusRules = useMemo(
    () =>
      model.rules
        .filter((r) => r.agent_id === focusId)
        .sort((a, b) => b.support - a.support)
        .slice(0, 8),
    [model.rules, focusId]
  );
  const q = pressure.get(focusId);

  const onNodeClick = useCallback(
    (_: unknown, n: Node) => {
      if (n.type === "agent") onSelect(String(n.id));
    },
    [onSelect]
  );

  return (
    <div className="blanket-wrap">
      <div className="blanket-legend">
        <span>
          <i className="bl-tag in" /> Кто передаёт дела сюда ({nb.parents.length})
        </span>
        <span>
          <i className="bl-tag focus" /> Выбранный сотрудник
        </span>
        <span>
          <i className="bl-tag out" /> Кому уходит дальше ({nb.children.length})
        </span>
        <span>
          <i className="bl-tag peer" /> Коллеги в подразделении ({nb.peers.length})
        </span>
      </div>
      <div className="blanket-body">
        <div className="flow-canvas blanket-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            onInit={(inst) => {
              rfRef.current = inst;
              inst.fitView({ padding: 0.2, duration: 0 });
            }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable={false}
            onlyRenderVisibleElements
            minZoom={0.25}
            maxZoom={2}
            onNodeClick={onNodeClick}
          >
            <Background color={tokens.colors.line} gap={21} />
            <Controls showInteractive={false} />
            <Panel position="top-left" className="rf-panel-ru">
              <div className="org-explain-card">
                <strong>{focus ? agentTitle(focus.id, model.donor_id) : focusId}</strong>
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  {focus ? roleTitle(focus.role_id, model.donor_id) : ""}
                  {focus && agentWhat(focus.id, model.donor_id)
                    ? ` — ${agentWhat(focus.id, model.donor_id)}`
                    : ""}
                </p>
                <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
                  событий {focus?.n_events ?? "—"} · застревание{" "}
                  {focus?.stuck_frac != null ? `${(focus.stuck_frac * 100).toFixed(0)}%` : "—"} ·
                  очередь {q != null ? q.toFixed(2) : "—"} · действий{" "}
                  {focus?.n_distinct_actions ?? "—"}
                </p>
              </div>
            </Panel>
          </ReactFlow>
        </div>
        <aside className="blanket-side">
          <h3>Сводка покрывала</h3>
          <div className="blanket-stats">
            <div>
              <strong>{nb.parents.length}</strong>
              входов · {(nb.inMass * 100).toFixed(0)}% массы
            </div>
            <div>
              <strong>{nb.children.length}</strong>
              выходов · {(nb.outMass * 100).toFixed(0)}% массы
            </div>
            <div>
              <strong>{nb.peers.length}</strong>
              коллег в отделе
            </div>
            <div>
              <strong>{focusRules.length}</strong>
              правил поведения
            </div>
          </div>
          <h3>Входит (handover)</h3>
          <LinkList
            items={nb.parents}
            model={model}
            empty="Нет входящих передач в логе"
            onSelect={onSelect}
            tone="in"
          />
          <h3>Уходит</h3>
          <LinkList
            items={nb.children}
            model={model}
            empty="Нет исходящих передач"
            onSelect={onSelect}
            tone="out"
          />
          <h3>Коллеги отдела</h3>
          <LinkList
            items={nb.peers}
            model={model}
            empty="Нет коллег"
            onSelect={onSelect}
            tone="peer"
          />
          <h3>Типичные правила фокуса</h3>
          <ul className="blanket-rules">
            {focusRules.length === 0 && <li className="muted">Мало данных</li>}
            {focusRules.map((r) => (
              <li key={`${r.input}-${r.top1_action}`}>
                <span className="mono">{r.top1_action}</span>
                <div className="muted">
                  после «{r.input}» → {(r.top1_mass * 100).toFixed(0)}% (n={r.support})
                </div>
              </li>
            ))}
          </ul>
          {focus && focus.exclusive_actions.length > 0 && (
            <>
              <h3>Делает почти один</h3>
              <ul className="blanket-rules">
                {focus.exclusive_actions.slice(0, 6).map((x) => (
                  <li key={x.action}>
                    <span className="mono">{x.action}</span>
                    <div className="muted">
                      {(x.share * 100).toFixed(0)}% · n={x.agent_n}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function LinkList({
  items,
  model,
  empty,
  onSelect,
  tone,
}: {
  items: Link[];
  model: OrgModel;
  empty: string;
  onSelect: (id: string) => void;
  tone: string;
}) {
  if (!items.length) return <p className="muted">{empty}</p>;
  return (
    <ul className={`blanket-links ${tone}`}>
      {items.map((l) => {
        const a = model.agents.find((x) => x.id === l.id);
        return (
          <li key={l.id}>
            <button type="button" className="linkish" onClick={() => onSelect(l.id)}>
              <strong>{agentTitle(l.id, model.donor_id)}</strong>
              <span className="muted">
                {a ? roleTitle(a.role_id, model.donor_id) : ""}
                {l.weight > 0 ? ` · доля ${(l.weight * 100).toFixed(0)}%` : ""}
                {l.est_handovers != null ? ` · ~${l.est_handovers} передач` : ""}
                {a ? ` · ${a.n_events} соб.` : ""}
                {a?.stuck_frac != null ? ` · застр. ${(a.stuck_frac * 100).toFixed(0)}%` : ""}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function mergeNodeData(prev: Node[], next: Node[]): Node[] {
  const byId = Object.fromEntries(next.map((n) => [n.id, n]));
  return prev
    .filter((n) => byId[n.id])
    .map((n) => ({
      ...n,
      data: { ...n.data, ...byId[n.id].data },
      position: n.position,
    }))
    .concat(next.filter((n) => !prev.some((p) => p.id === n.id)));
}

function neighborhood(model: OrgModel, focusId: string): Nb {
  const byAgent = Object.fromEntries(model.agents.map((a) => [a.id, a]));
  const focus = byAgent[focusId];
  const focusN = focus?.n_events ?? 0;
  const parents: Link[] = [];
  const children: Link[] = [];
  for (const e of model.edges) {
    if (e.to_agent === focusId && e.from_agent !== focusId) {
      const a = byAgent[e.from_agent];
      parents.push({
        id: e.from_agent,
        weight: e.weight,
        n_events: a?.n_events,
        stuck: a?.stuck_frac,
        role: a?.role_id,
        est_handovers: focusN > 0 ? Math.max(1, Math.round(e.weight * focusN)) : undefined,
      });
    }
    if (e.from_agent === focusId && e.to_agent !== focusId) {
      const a = byAgent[e.to_agent];
      children.push({
        id: e.to_agent,
        weight: e.weight,
        n_events: a?.n_events,
        stuck: a?.stuck_frac,
        role: a?.role_id,
        est_handovers: focusN > 0 ? Math.max(1, Math.round(e.weight * focusN)) : undefined,
      });
    }
  }
  parents.sort((a, b) => b.weight - a.weight);
  children.sort((a, b) => b.weight - a.weight);
  const peers: Link[] = focus
    ? model.agents
        .filter((a) => a.role_id === focus.role_id && a.id !== focusId)
        .sort((a, b) => b.n_events - a.n_events)
        .slice(0, 8)
        .map((a) => ({
          id: a.id,
          weight: 0,
          n_events: a.n_events,
          stuck: a.stuck_frac,
          role: a.role_id,
        }))
    : [];
  const topP = parents.slice(0, 10);
  const topC = children.slice(0, 10);
  return {
    parents: topP,
    children: topC,
    peers,
    inMass: topP.reduce((s, x) => s + x.weight, 0),
    outMass: topC.reduce((s, x) => s + x.weight, 0),
  };
}

function buildBlanket(
  model: OrgModel,
  focusId: string,
  nb: Nb,
  pressure: Map<string, number>
): { nodes: Node[]; edges: Edge[] } {
  const byId = Object.fromEntries(model.agents.map((a) => [a.id, a]));
  const CX = 480;
  const CY = 280;
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const c = tokens.colors;

  const placeAgent = (
    id: string,
    x: number,
    y: number,
    zone: "in" | "focus" | "out" | "peer",
    weight?: number,
    est?: number
  ) => {
    const a = byId[id];
    if (!a) return;
    const p = pressure.get(id);
    const w = weight != null ? ` · ${(weight * 100).toFixed(0)}%` : "";
    const h = est != null ? ` · ~${est} пер.` : "";
    const stuck =
      a.stuck_frac != null ? ` · застр. ${(a.stuck_frac * 100).toFixed(0)}%` : "";
    nodes.push({
      id,
      type: "agent",
      position: { x, y },
      data: {
        label: agentShort(id, model.donor_id),
        fullLabel: `${agentTitle(id, model.donor_id)} · ${roleTitle(a.role_id, model.donor_id)} · ${zoneLabel(zone)}${w}${h} · ${a.n_events} соб.${stuck}`,
        size: zone === "focus" ? 68 : zone === "peer" ? 36 : 48,
        stroke: zone === "focus" ? c.accent : congestionStroke(a.stuck_frac, p),
        capacity: a.capacity,
        origin: a.origin,
        queueMark: (p ?? 0) >= 0.4,
        selected: zone === "focus",
      },
    });
  };

  placeAgent(focusId, CX, CY, "focus");

  nb.parents.forEach((p, i) => {
    placeAgent(p.id, 40, 24 + i * 52, "in", p.weight, p.est_handovers);
    edges.push({
      id: `in-${p.id}`,
      source: p.id,
      target: focusId,
      label: p.weight >= 0.12 ? `${Math.round(p.weight * 100)}%` : undefined,
      animated: false,
      style: { stroke: c.info, strokeWidth: 1.25 + p.weight * 4 },
      labelStyle: { fontSize: 10, fill: c.inkMuted },
      labelBgStyle: { fill: c.surface, fillOpacity: 0.85 },
      markerEnd: { type: MarkerType.ArrowClosed, color: c.info, width: 12, height: 12 },
    });
  });

  nb.children.forEach((ch, i) => {
    placeAgent(ch.id, 920, 24 + i * 52, "out", ch.weight, ch.est_handovers);
    edges.push({
      id: `out-${ch.id}`,
      source: focusId,
      target: ch.id,
      label: ch.weight >= 0.12 ? `${Math.round(ch.weight * 100)}%` : undefined,
      animated: false,
      style: { stroke: c.accent, strokeWidth: 1.25 + ch.weight * 4 },
      labelStyle: { fontSize: 10, fill: c.inkMuted },
      labelBgStyle: { fill: c.surface, fillOpacity: 0.85 },
      markerEnd: { type: MarkerType.ArrowClosed, color: c.accent, width: 12, height: 12 },
    });
  });

  nb.peers.forEach((peer, i) => {
    const col = i % 4;
    const row = Math.floor(i / 4);
    placeAgent(peer.id, 300 + col * 100, 460 + row * 72, "peer");
  });

  return { nodes, edges };
}

function zoneLabel(z: string): string {
  if (z === "in") return "передаёт сюда";
  if (z === "out") return "получает отсюда";
  if (z === "peer") return "коллега";
  return "фокус";
}
