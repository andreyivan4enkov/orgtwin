import type { CSSProperties } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

type OrgData = {
  label: string;
  subtitle?: string;
  selected?: boolean;
  dim?: boolean;
};
type RoleData = {
  label: string;
  subtitle?: string;
  hint?: string;
  n: number;
  selected?: boolean;
  dim?: boolean;
  congested?: boolean;
  critical?: boolean;
};
type AgentData = {
  label: string;
  fullLabel?: string;
  size: number;
  stroke: string;
  capacity: number;
  origin: string;
  selected?: boolean;
  dim?: boolean;
  queueMark?: boolean;
  queueValue?: number;
  pulse?: boolean;
};

export function OrgNode({ data }: NodeProps) {
  const d = data as OrgData;
  return (
    <div className={`rf-org${d.selected ? " selected" : ""}${d.dim ? " dim" : ""}`}>
      {d.subtitle && <div className="rf-level">{d.subtitle}</div>}
      <div className="rf-title">{d.label}</div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

export function RoleNode({ data }: NodeProps) {
  const d = data as RoleData;
  return (
    <div
      className={`rf-role${d.selected ? " selected" : ""}${d.dim ? " dim" : ""}${
        d.critical ? " critical" : d.congested ? " congested" : ""
      }`}
      title={d.hint}
    >
      <div className="rf-level">подразделение</div>
      <div className="rf-title">{d.label}</div>
      <div className="muted">{d.subtitle || `${d.n} чел.`}</div>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

export function AgentNode({ data }: NodeProps) {
  const d = data as AgentData;
  const manual = d.origin === "manual" || d.origin === "hybrid";
  return (
    <div
      className={`rf-agent${manual ? " manual" : ""}${d.selected ? " selected" : ""}${
        d.dim ? " dim" : ""
      }${d.queueMark ? " queued" : ""}${d.pulse ? " pulse" : ""}`}
      style={
        {
          "--node-size": `${d.size}px`,
          "--node-stroke": d.stroke,
          cursor: "pointer",
        } as CSSProperties
      }
      title={d.fullLabel || d.label}
    >
      <span className="rf-agent-label">{d.label}</span>
      {d.queueValue != null && d.queueValue > 0 && (
        <span className="queue-value" title={`Очередь: ${d.queueValue}`}>
          {d.queueValue}
        </span>
      )}
      {d.capacity > 0 && <span className="slot-mark" title="Слот занятости" />}
      {d.queueMark && <span className="queue-mark" title="Очередь / затор" />}
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

export const nodeTypes = {
  org: OrgNode,
  role: RoleNode,
  agent: AgentNode,
};
