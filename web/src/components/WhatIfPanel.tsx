import { useState } from "react";
import type { OrgModel, WhatIfResult } from "../lib/api";
import { api } from "../lib/api";
import { agentTitle, roleTitle } from "../lib/orgLabels";

export type WhatIfState = {
  excludeAgents: string[];
  excludeRoles: string[];
  roleMultipliers: Record<string, number>;
  globalMultiplier: number;
};

export const emptyWhatIf = (): WhatIfState => ({
  excludeAgents: [],
  excludeRoles: [],
  roleMultipliers: {},
  globalMultiplier: 1,
});

export function WhatIfPanel({
  donorId,
  model,
  state,
  onChange,
  result,
  onResult,
}: {
  donorId: string;
  model: OrgModel;
  state: WhatIfState;
  onChange: (s: WhatIfState) => void;
  result: WhatIfResult | null;
  onResult: (r: WhatIfResult | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [roleLoad, setRoleLoad] = useState(model.roles[0]?.id || "");

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.whatIf(donorId, {
        exclude_agents: state.excludeAgents,
        exclude_roles: state.excludeRoles,
        role_multipliers: state.roleMultipliers,
        global_multiplier: state.globalMultiplier,
      });
      onResult(r);
    } catch (e) {
      setErr(String(e));
      onResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="whatif-panel">
      <h2 className="section-title">Сценарий «что если»</h2>
      <p className="muted">
        Вычеркните сотрудника или подразделение и/или поднимите нагрузку только у одного
        отдела — не у всей компании. Затем нажмите «Просчитать».
      </p>

      <div className="whatif-chips">
        <span className="muted">Исключены люди:</span>
        {state.excludeAgents.length === 0 && <span className="muted">нет</span>}
        {state.excludeAgents.map((id) => (
          <button
            key={id}
            type="button"
            className="chip"
            onClick={() =>
              onChange({
                ...state,
                excludeAgents: state.excludeAgents.filter((x) => x !== id),
              })
            }
            title="Вернуть в модель"
          >
            {agentTitle(id, model.donor_id)} ×
          </button>
        ))}
      </div>

      <div className="whatif-chips">
        <span className="muted">Исключены подразделения:</span>
        {state.excludeRoles.length === 0 && <span className="muted">нет</span>}
        {state.excludeRoles.map((id) => (
          <button
            key={id}
            type="button"
            className="chip"
            onClick={() =>
              onChange({
                ...state,
                excludeRoles: state.excludeRoles.filter((x) => x !== id),
              })
            }
          >
            {roleTitle(id, model.donor_id)} ×
          </button>
        ))}
      </div>

      <div className="whatif-row">
        <label>
          Нагрузка только на подразделение
          <select value={roleLoad} onChange={(e) => setRoleLoad(e.target.value)}>
            {model.roles.map((r) => (
              <option key={r.id} value={r.id}>
                {roleTitle(r.id, model.donor_id)}
              </option>
            ))}
          </select>
        </label>
        <div className="segment">
          {[1, 1.5, 2].map((m) => (
            <button
              key={m}
              type="button"
              className={state.roleMultipliers[roleLoad] === m ? "active" : ""}
              onClick={() =>
                onChange({
                  ...state,
                  roleMultipliers: { ...state.roleMultipliers, [roleLoad]: m },
                  globalMultiplier: 1,
                })
              }
            >
              ×{m}
            </button>
          ))}
        </div>
      </div>

      <div className="whatif-row">
        <span className="muted">Глобальный поток (вся компания)</span>
        <div className="segment">
          {[1, 2].map((m) => (
            <button
              key={m}
              type="button"
              className={state.globalMultiplier === m ? "active" : ""}
              onClick={() =>
                onChange({
                  ...state,
                  globalMultiplier: m,
                  roleMultipliers: {},
                })
              }
            >
              ×{m}
            </button>
          ))}
        </div>
      </div>

      <div className="whatif-actions">
        <button type="button" className="btn" disabled={busy} onClick={() => void run()}>
          {busy ? "Считаем…" : "Просчитать сценарий"}
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            onChange(emptyWhatIf());
            onResult(null);
          }}
        >
          Сбросить
        </button>
      </div>

      {err && <p className="error-banner">{err}</p>}

      {result && (
        <div className="whatif-result">
          <div className="metric-row">
            <div className="metric">
              <div className="val">{result.baseline.max_queue_any_real}</div>
              <div className="lbl">очередь база</div>
            </div>
            <div className="metric">
              <div className="val">{result.scenario.max_queue_any_real}</div>
              <div className="lbl">очередь сценарий</div>
            </div>
            <div className="metric">
              <div className={`val${result.delta_max_queue > 0 ? " danger-text" : ""}`}>
                {result.delta_max_queue > 0 ? "+" : ""}
                {result.delta_max_queue}
              </div>
              <div className="lbl">изменение</div>
            </div>
          </div>
          <p className="muted">
            Узкое место сейчас:{" "}
            {result.scenario.bottleneck_agent
              ? agentTitle(result.scenario.bottleneck_agent, model.donor_id)
              : "—"}
          </p>
        </div>
      )}
    </div>
  );
}
