import { useEffect, useMemo, useRef } from "react";
import {
  ReactFlow,
  Background,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  Panel,
} from "@xyflow/react";
import type { OrgModel, QueueSlice } from "../lib/api";
import { tokens } from "../lib/tokens";
import {
  agentSize,
  congestionStroke,
  hasCollisions,
  layoutOrgTree,
  queuePressureMap,
} from "../lib/layout";
import {
  agentShort,
  agentTitle,
  donorOrgMeta,
  roleTitle,
  roleWhat,
} from "../lib/orgLabels";
import { nodeTypes } from "./EntityNodes";

export function OrgMap({
  model,
  selectedId,
  onSelect,
  queueSlice,
  playing,
}: {
  model: OrgModel;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  queueSlice?: QueueSlice | null;
  playing?: boolean;
}) {
  const pressure = useMemo(() => queuePressureMap(queueSlice), [queueSlice]);
  const layout = useMemo(() => layoutOrgTree(model), [model]);
  const collision = hasCollisions(layout.boxes);
  const meta = donorOrgMeta(model.donor_id);

  const built = useMemo(
    () => buildOrgChart(model, layout, selectedId, pressure, playing ?? false),
    [model, layout, selectedId, pressure, playing]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(built.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(built.edges);
  const posRef = useRef(layout.positions);

  useEffect(() => {
    posRef.current = layout.positions;
    setNodes(built.nodes);
    setEdges(built.edges);
  }, [built, layout.positions, setNodes, setEdges]);

  return (
    <div className="flow-canvas org-chart">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.15}
        maxZoom={1.8}
        nodesDraggable
        onNodeClick={(_, n) => {
          if (n.type === "agent") onSelect(String(n.id));
          if (n.type === "role") onSelect(String(n.id).replace(/^role:/, ""));
          if (n.type === "org") onSelect(null);
        }}
        onPaneClick={() => onSelect(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color={tokens.colors.line} gap={21} />
        <Panel position="top-left" className="rf-panel-ru org-explain">
          <div className="org-explain-card">
            <strong>Структура компании (из журнала работ)</strong>
            <p>
              Сверху вниз: <em>организация</em> → <em>подразделения</em> → <em>сотрудники</em>.
            </p>
            <p className="muted">{meta.structureNote}</p>
            {collision && <p className="danger-text">Обнаружено пересечение узлов</p>}
          </div>
        </Panel>
        <Panel position="bottom-left" className="rf-panel-ru">
          <div className="zoom-hint muted">
            Колёсико — масштаб · перетащите узел · клик — карточка справа
          </div>
        </Panel>
        {queueSlice?.bottleneck_agent && (
          <Panel position="top-right" className="rf-panel-ru">
            <span className="badge danger-badge">
              Узкое место: {agentTitle(queueSlice.bottleneck_agent, model.donor_id)}
            </span>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}

function buildOrgChart(
  model: OrgModel,
  layout: ReturnType<typeof layoutOrgTree>,
  selectedId: string | null,
  pressure: Map<string, number>,
  playing: boolean
): { nodes: Node[]; edges: Edge[] } {
  const { positions, visibleAgents, visibleRoles } = layout;
  const maxN = Math.max(...visibleAgents.map((a) => a.n_events), 1);
  const meta = donorOrgMeta(model.donor_id);

  const roleCongestion = new Map<string, number>();
  for (const a of visibleAgents) {
    const p = pressure.get(a.id) || 0;
    roleCongestion.set(a.role_id, Math.max(roleCongestion.get(a.role_id) || 0, p));
  }

  const nodes: Node[] = [
    {
      id: "org",
      type: "org",
      position: positions.org,
      data: {
        label: meta.company,
        subtitle: "организация",
        selected: false,
        dim: false,
      },
    },
  ];

  for (const r of visibleRoles) {
    const cong = roleCongestion.get(r.id) || 0;
    const title = roleTitle(r.id, model.donor_id);
    nodes.push({
      id: `role:${r.id}`,
      type: "role",
      position: positions[`role:${r.id}`],
      data: {
        label: title,
        subtitle: `подразделение · ${r.n_agents} чел.`,
        hint: roleWhat(r.id, model.donor_id),
        n: r.n_agents,
        congested: cong >= 0.4,
        critical: cong >= 0.75,
        selected: selectedId === r.id,
        dim: !!selectedId && selectedId !== r.id,
      },
    });
  }

  for (const a of visibleAgents) {
    const p = pressure.get(a.id);
    nodes.push({
      id: a.id,
      type: "agent",
      position: positions[a.id],
      data: {
        label: agentShort(a.id, model.donor_id),
        fullLabel: agentTitle(a.id, model.donor_id),
        size: agentSize(a.n_events, maxN),
        stroke: congestionStroke(a.stuck_frac, p),
        capacity: a.capacity,
        origin: a.origin,
        queueMark: (p ?? 0) >= 0.4,
        pulse: playing && (p ?? 0) >= 0.75,
        selected: selectedId === a.id,
        dim: !!selectedId && selectedId !== a.id,
      },
    });
  }

  // Только иерархия оргсхемы — без процессных стрелок handover
  const edges: Edge[] = [
    ...visibleRoles.map((r) => ({
      id: `e-org-${r.id}`,
      source: "org",
      target: `role:${r.id}`,
      style: { stroke: tokens.colors.ink, strokeWidth: 1.5, opacity: 0.35 },
    })),
    ...visibleAgents.map((a) => ({
      id: `e-role-${a.id}`,
      source: `role:${a.role_id}`,
      target: a.id,
      style: { stroke: tokens.colors.line, strokeWidth: 1.25 },
    })),
  ];

  return { nodes, edges };
}
