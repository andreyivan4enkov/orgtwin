import { useEffect, useState } from "react";
import { api, type DesignState, type OrgModel } from "../lib/api";

export function DesignView({
  donorId,
  model,
  onSaved,
}: {
  donorId: string;
  model: OrgModel;
  onSaved: () => void;
}) {
  const [design, setDesign] = useState<DesignState>({
    roles: [],
    agents: [],
    edges: [],
    capacities: {},
  });
  const [roleId, setRoleId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [agentRole, setAgentRole] = useState("");
  const [capAgent, setCapAgent] = useState("");
  const [capVal, setCapVal] = useState("2");
  const [edgeFrom, setEdgeFrom] = useState("");
  const [edgeTo, setEdgeTo] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getDesign(donorId).then(setDesign).catch((e) => setMsg(String(e)));
  }, [donorId]);

  async function save(next: DesignState) {
    setMsg("Сохранение…");
    const saved = await api.putDesign(donorId, next);
    setDesign(saved);
    setMsg("Сохранено. На карте ручные узлы — пунктиром.");
    onSaved();
  }

  const manualCount = model.agents.filter((a) => a.origin !== "log").length;

  return (
    <div style={{ padding: "var(--space-4)", overflow: "auto", height: "100%" }}>
      <p className="muted" style={{ maxWidth: 560 }}>
        Проектирование: добавьте роли и сотрудников вручную, если лог кривой или вы
        собираете структуру с нуля. Всё ручное на карте рисуется пунктиром.
      </p>

      <div className="design-form" style={{ maxWidth: 420 }}>
        <strong>Роль / отдел</strong>
        <input
          placeholder="название роли"
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (!roleId.trim()) return;
            void save({
              ...design,
              roles: [
                ...design.roles.filter((r) => r.id !== roleId),
                { id: roleId.trim(), label: roleId.trim() },
              ],
            });
            setRoleId("");
          }}
        >
          Добавить роль
        </button>

        <strong>Сотрудник</strong>
        <input
          placeholder="идентификатор сотрудника"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
        />
        <input
          placeholder="к какой роли относится"
          value={agentRole}
          onChange={(e) => setAgentRole(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (!agentId.trim()) return;
            void save({
              ...design,
              agents: [
                ...design.agents.filter((a) => a.id !== agentId),
                { id: agentId.trim(), role_id: agentRole.trim() || "вручную", capacity: 1 },
              ],
            });
            setAgentId("");
          }}
        >
          Добавить сотрудника
        </button>

        <strong>Слоты занятости</strong>
        <p className="muted" style={{ margin: 0 }}>
          Сколько дел сотрудник может вести параллельно (по умолчанию 1).
        </p>
        <input
          placeholder="идентификатор сотрудника"
          value={capAgent}
          onChange={(e) => setCapAgent(e.target.value)}
        />
        <input value={capVal} onChange={(e) => setCapVal(e.target.value)} />
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (!capAgent.trim()) return;
            void save({
              ...design,
              capacities: { ...design.capacities, [capAgent.trim()]: Number(capVal) || 1 },
            });
          }}
        >
          Задать слоты
        </button>

        <strong>Передача дел</strong>
        <p className="muted" style={{ margin: 0 }}>
          Связь «от кого → кому» обычно уходят кейсы.
        </p>
        <input
          placeholder="от сотрудника"
          value={edgeFrom}
          onChange={(e) => setEdgeFrom(e.target.value)}
        />
        <input
          placeholder="к сотруднику"
          value={edgeTo}
          onChange={(e) => setEdgeTo(e.target.value)}
        />
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (!edgeFrom.trim() || !edgeTo.trim()) return;
            void save({
              ...design,
              edges: [
                ...design.edges,
                { from_agent: edgeFrom.trim(), to_agent: edgeTo.trim(), weight: 1 },
              ],
            });
            setEdgeFrom("");
            setEdgeTo("");
          }}
        >
          Добавить связь
        </button>
      </div>

      {msg && <p className="muted">{msg}</p>}

      <h2 className="section-title">Ручные правки сейчас</h2>
      <ul className="rule-list">
        <li>Ролей: {design.roles.length}</li>
        <li>Сотрудников: {design.agents.length}</li>
        <li>Связей: {design.edges.length}</li>
        <li>Слотов задано: {Object.keys(design.capacities).length}</li>
      </ul>
      <p className="muted">
        В модели сотрудников: {model.agents.length}, из них ручных/смешанных: {manualCount}
      </p>
    </div>
  );
}
