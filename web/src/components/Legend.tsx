import { entityLegend } from "../lib/tokens";

export function Legend() {
  return (
    <div className="legend">
      {entityLegend.map((e) => (
        <div className="legend-row" key={e.kind}>
          <Signature kind={e.kind} />
          <span>
            {e.label}
            <span className="muted"> — {e.shape}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export function Signature({ kind }: { kind: string }) {
  if (kind === "org") return <div className="sig sig-org" />;
  if (kind === "role") return <div className="sig sig-role" />;
  if (kind === "agent")
    return (
      <div className="sig sig-agent">
        <span className="slot" />
      </div>
    );
  if (kind === "action") return <div className="sig sig-action" />;
  if (kind === "case") return <div className="sig sig-case" />;
  if (kind === "queue")
    return (
      <div className="sig sig-queue">
        <i />
        <i />
        <i />
      </div>
    );
  if (kind === "manual") return <div className="sig sig-manual" />;
  if (kind === "slot")
    return (
      <div className="sig sig-agent">
        <span className="slot" />
      </div>
    );
  return null;
}
