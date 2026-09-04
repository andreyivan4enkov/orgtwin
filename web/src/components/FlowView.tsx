import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  MarkerType,
  Panel,
} from "@xyflow/react";
import { motion } from "framer-motion";
import type { OrgModel, QueueSlice } from "../lib/api";
import { tokens } from "../lib/tokens";
import {
  congestionStroke,
  hasCollisions,
  layoutFlowLoad,
  queuePressureMap,
  type SliceKey,
} from "../lib/layout";
import { SLICE_RU } from "../lib/labels";
import { agentShort, agentTitle, roleTitle } from "../lib/orgLabels";
import { useTheme } from "../lib/theme";
import { nodeTypes } from "./EntityNodes";

function pressureSig(pressure: Map<string, number>): string {
  if (!pressure.size) return "";
  const parts: string[] = [];
  pressure.forEach((v, k) => parts.push(`${k}:${v.toFixed(2)}`));
  return parts.join("|");
}

/** Единый режим: поток передач + нагрузка/очереди. */
export function FlowView({
  model,
  slice,
  queueSlice,
  playing,
  selectedId,
  onSelect,
}: {
  model: OrgModel;
  slice: SliceKey;
  queueSlice?: QueueSlice | null;
  playing: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const { theme } = useTheme();
  const q = model.queue_slices;
  const current = queueSlice || q?.[slice] || null;
  const sample = model.flow_sample || [];
  const [tick, setTick] = useState(0);
  const pressure = useMemo(() => queuePressureMap(current), [current]);
  const pSig = useMemo(() => pressureSig(pressure), [pressure]);
  const queueById = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of current?.top_agents || []) m.set(r.id, r.max_queue);
    return m;
  }, [current]);

  const maxBar = useMemo(() => {
    if (!q) return 1;
    return Math.max(
      q.x1.max_queue_any_real || 0,
      q.x2.max_queue_any_real || 0,
      q.x2_plus1?.max_queue_any_real || 0,
      1
    );
  }, [q]);

  const grid = useMemo(() => layoutFlowLoad(model, current, 20), [model, current]);
  const collision = hasCollisions(grid.boxes);

  const baseLayout = useMemo(
    () => buildFlowLoadGraph(model, grid, pressure, queueById),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [model, grid, pSig, queueById, theme]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(baseLayout.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(baseLayout.edges);

  useEffect(() => {
    setNodes(
      baseLayout.nodes.map((n) => ({
        ...n,
        data: {
          ...n.data,
          size: selectedId === n.id ? 56 : 48,
          selected: selectedId === n.id,
          dim: !!selectedId && selectedId !== n.id,
          pulse: playing && Boolean((n.data as { queueMark?: boolean }).queueMark),
        },
      }))
    );
    setEdges(
      baseLayout.edges.map((e) => {
        const involve = !selectedId || selectedId === e.source || selectedId === e.target;
        return {
          ...e,
          style: { ...e.style, opacity: involve ? 0.85 : 0.22 },
          labelStyle: { ...(e.labelStyle || {}), opacity: involve ? 1 : 0.2 },
          animated: playing && involve,
        };
      })
    );
  }, [baseLayout, selectedId, playing, setNodes, setEdges]);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 700);
    return () => window.clearInterval(id);
  }, [playing]);

  const tokensOnEdges = useMemo(() => {
    if (!playing) return [];
    const out: { key: string; x: number; y: number; hot: boolean }[] = [];
    const pos = grid.positions;
    sample.slice(0, 8).forEach((path, pi) => {
      const step = (tick + pi) % Math.max(path.agents.length - 1, 1);
      const a = path.agents[step];
      const b = path.agents[step + 1] || a;
      const pa = pos[a];
      const pb = pos[b];
      if (!pa || !pb) return;
      const t = (tick * 0.15 + pi * 0.07) % 1;
      const hot = (pressure.get(a) || 0) >= 0.4 || (pressure.get(b) || 0) >= 0.4;
      out.push({
        key: `${path.case_id}-${step}`,
        x: pa.x + 24 + (pb.x - pa.x) * t,
        y: pa.y + 24 + (pb.y - pa.y) * t,
        hot,
      });
    });
    return out;
  }, [sample, tick, grid.positions, playing, pressure]);

  const meta = SLICE_RU[slice];
  const rows = current?.top_agents || [];

  const onNodeClick = useCallback(
    (_: unknown, n: Node) => {
      if (n.type === "agent") onSelect(String(n.id));
    },
    [onSelect]
  );

  return (
    <div className="stress-layout flow-load">
      <aside className="stress-side">
        <h2 className="section-title">Поток и нагрузка</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Слева — кто отдаёт дела, справа — кто принимает. Цвет и квадратик — очередь в срезе{" "}
          <strong>{meta?.short ?? slice}</strong>. Клик — пояснение.
        </p>

        {!current ? (
          <div className="status-banner">
            Очереди ещё не посчитаны. Нажмите «Пересобрать» в шапке.
          </div>
        ) : (
          <>
            <div className="metric-row">
              <div className="metric">
                <div className="val">{current.max_queue_any_real ?? "—"}</div>
                <div className="lbl">макс. очередь</div>
              </div>
              <div className="metric">
                <div className="val" style={{ fontSize: 15 }}>
                  {current.bottleneck_agent
                    ? agentTitle(current.bottleneck_agent, model.donor_id)
                    : "—"}
                </div>
                <div className="lbl">узкое место</div>
              </div>
            </div>

            <h2 className="section-title">Очереди у сотрудников</h2>
            <div className="queue-bars">
              {rows.map((r) => {
                const hot = (pressure.get(r.id) || 0) >= 0.75;
                const warm = (pressure.get(r.id) || 0) >= 0.4;
                const sel = selectedId === r.id;
                return (
                  <button
                    type="button"
                    className={`queue-row clickable${sel ? " selected" : ""}`}
                    key={r.id}
                    onClick={() => onSelect(r.id)}
                    title="Открыть пояснение"
                  >
                    <span className={hot ? "danger-text" : ""}>
                      {agentTitle(r.id, model.donor_id)}
                    </span>
                    <div className="queue-bar-track">
                      <div
                        className={`queue-bar-fill${hot ? " critical" : warm ? " warn" : ""}`}
                        style={{
                          width: `${Math.min(100, (r.max_queue / maxBar) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="mono">{r.max_queue}</span>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </aside>

      <div className="stress-map" style={{ position: "relative" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          proOptions={{ hideAttribution: true }}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable={false}
          onlyRenderVisibleElements
          minZoom={0.25}
          maxZoom={1.8}
          onNodeClick={onNodeClick}
          onPaneClick={() => onSelect(null)}
        >
          <Background color={tokens.colors.line} gap={21} />
          <Controls showInteractive={false} />
          <Panel position="top-left" className="rf-panel-ru">
            <div className="org-explain-card">
              <strong>Пути передач + очереди</strong>
              <p className="muted" style={{ margin: "6px 0 0" }}>
                Стрелки — handover. Красный — очередь.{" "}
                {playing ? "Анимация запущена." : "«Пуск» — анимация кейсов."}
              </p>
              {collision && <p className="danger-text">Пересечение узлов</p>}
              {current?.bottleneck_agent && (
                <p className="danger-text" style={{ marginTop: 6 }}>
                  Затор: {agentTitle(current.bottleneck_agent, model.donor_id)}
                </p>
              )}
            </div>
          </Panel>
        </ReactFlow>
        {tokensOnEdges.map((tok) => (
          <motion.div
            key={tok.key}
            className={`case-token${tok.hot ? " hot" : ""}`}
            animate={{ left: tok.x, top: tok.y }}
            transition={{ duration: 0.55, ease: "easeInOut" }}
            style={{ left: tok.x, top: tok.y }}
          />
        ))}
      </div>
    </div>
  );
}

function buildFlowLoadGraph(
  model: OrgModel,
  grid: ReturnType<typeof layoutFlowLoad>,
  pressure: Map<string, number>,
  queueById: Map<string, number>
): { nodes: Node[]; edges: Edge[] } {
  const ids = new Set(grid.agents.map((a) => a.id));
  const c = tokens.colors;
  const nodes: Node[] = grid.agents.map((a) => {
    const p = pressure.get(a.id);
    const qn = queueById.get(a.id);
    return {
      id: a.id,
      type: "agent",
      position: grid.positions[a.id],
      data: {
        label: agentShort(a.id, model.donor_id),
        fullLabel: [
          agentTitle(a.id, model.donor_id),
          roleTitle(a.role_id, model.donor_id),
          `${a.n_events} соб.`,
          qn != null ? `очередь ${qn}` : null,
          "клик — пояснение",
        ]
          .filter(Boolean)
          .join(" · "),
        size: 48,
        stroke: congestionStroke(a.stuck_frac, p),
        capacity: a.capacity,
        origin: a.origin,
        queueMark: (p ?? 0) >= 0.4,
        queueValue: qn,
        pulse: false,
        selected: false,
        dim: false,
      },
    };
  });

  const edges: Edge[] = model.edges
    .filter((e) => ids.has(e.from_agent) && ids.has(e.to_agent) && e.from_agent !== e.to_agent)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 28)
    .map((e) => {
      const hot =
        (pressure.get(e.from_agent) || 0) >= 0.4 || (pressure.get(e.to_agent) || 0) >= 0.4;
      return {
        id: `${e.from_agent}->${e.to_agent}`,
        source: e.from_agent,
        target: e.to_agent,
        label: e.weight >= 0.15 ? `${Math.round(e.weight * 100)}%` : undefined,
        animated: false,
        style: {
          stroke: hot ? c.danger : c.info,
          strokeWidth: 1.2 + e.weight * 4,
          opacity: 0.75,
        },
        labelStyle: { fontSize: 10, fill: c.inkMuted },
        labelBgStyle: { fill: c.surface, fillOpacity: 0.8 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 12,
          height: 12,
          color: hot ? c.danger : c.info,
        },
      };
    });

  return { nodes, edges };
}
