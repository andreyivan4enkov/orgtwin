import type { Agent, OrgModel, QueueSlice, Rule } from "../lib/api";
import { originLabel } from "../lib/labels";
import { agentTitle, agentWhat, roleTitle, roleWhat } from "../lib/orgLabels";
import type { ProblemExplain } from "../lib/problems";
import { Legend, Signature } from "./Legend";

export function InspectPanel({
  model,
  selectedId,
  queueSlice,
  problem,
  onShowProblem,
  onExcludeAgent,
  onExcludeRole,
  onBoostRole,
}: {
  model: OrgModel | null;
  selectedId: string | null;
  queueSlice?: QueueSlice | null;
  problem?: ProblemExplain | null;
  onShowProblem?: () => void;
  onExcludeAgent?: (id: string) => void;
  onExcludeRole?: (id: string) => void;
  onBoostRole?: (id: string) => void;
}) {
  if (!model) {
    return (
      <aside className="inspect">
        <h2>Карточка</h2>
        <p className="muted">Выберите подразделение или сотрудника.</p>
        <details className="legend-details">
          <summary>Легенда значков</summary>
          <Legend />
        </details>
      </aside>
    );
  }

  const agent: Agent | undefined = model.agents.find((a) => a.id === selectedId);
  const role = model.roles.find((r) => r.id === selectedId || `role:${r.id}` === selectedId);
  const rules: Rule[] = agent ? model.rules.filter((r) => r.agent_id === agent.id) : [];
  const qRow = agent
    ? queueSlice?.top_agents.find((t) => t.id === agent.id)
    : undefined;

  return (
    <aside className="inspect">
      <h2>Карточка</h2>

      {onShowProblem && (
        <button type="button" className="btn ghost show-problem-btn" onClick={onShowProblem}>
          Показать пояснение
        </button>
      )}

      {problem && (
        <div className={`inline-problem ${problem.severity}`}>
          <strong>{problem.title}</strong>
          <p>{problem.meaning}</p>
          <p className="muted">{problem.blocks}</p>
        </div>
      )}

      {!selectedId && (
        <>
          <p className="muted">
            Клик по красному участку или сотруднику — здесь появится, <strong>что не так</strong> и{" "}
            <strong>что делать</strong>.
          </p>
          {model.metrics && (
            <div className="predict-block">
              <h2>Предсказание следующего шага</h2>
              <div className="metric-row">
                <div className="metric">
                  <div className="val">
                    {model.metrics.top3 != null
                      ? `${(model.metrics.top3 * 100).toFixed(1)}%`
                      : "—"}
                  </div>
                  <div className="lbl">факт в топ-3 предсказаний</div>
                </div>
                <div className="metric">
                  <div className="val">
                    {model.metrics.next_step != null
                      ? `${(model.metrics.next_step * 100).toFixed(1)}%`
                      : "—"}
                  </div>
                  <div className="lbl">точное предсказание (топ-1)</div>
                </div>
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Holdout: модель видит прошлое кейса и предсказывает следующее действие агента
                {model.metrics.n ? ` · n=${model.metrics.n}` : ""}
                {model.metrics.policy_kind ? ` · ${model.metrics.policy_kind}` : ""}.
                Топ-1 на ветвящихся процессах ниже топ-3 — ожидаемо.
              </p>
            </div>
          )}
        </>
      )}

      {agent && (
        <div>
          <div style={{ display: "flex", gap: 13, alignItems: "center", marginBottom: 13 }}>
            <Signature kind="agent" />
            <div>
              <div style={{ fontSize: 21 }}>{agentTitle(agent.id, model.donor_id)}</div>
              {agentWhat(agent.id, model.donor_id) && (
                <div className="muted">{agentWhat(agent.id, model.donor_id)}</div>
              )}
              <div className="muted">{roleTitle(agent.role_id, model.donor_id)}</div>
            </div>
            {agent.origin !== "log" && (
              <span className="badge manual">{originLabel(agent.origin)}</span>
            )}
          </div>
          <div className="metric-row">
            <div className="metric">
              <div className="val">{agent.n_events}</div>
              <div className="lbl">событий</div>
            </div>
            <div className="metric">
              <div className="val">
                {agent.stuck_frac != null ? `${(agent.stuck_frac * 100).toFixed(0)}%` : "—"}
              </div>
              <div className="lbl">застревание</div>
            </div>
            <div className="metric">
              <div className="val">{qRow?.max_queue ?? "—"}</div>
              <div className="lbl">очередь в срезе</div>
            </div>
          </div>

          <div className="inspect-actions">
            <button
              type="button"
              className="btn"
              onClick={() => onExcludeAgent?.(agent.id)}
              title="Убрать из модели и пересчитать сценарий"
            >
              Вычеркнуть сотрудника
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => onExcludeRole?.(agent.role_id)}
            >
              Вычеркнуть его отдел
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => onBoostRole?.(agent.role_id)}
            >
              Нагрузка ×2 только на отдел
            </button>
          </div>

          <h2>Типичные правила</h2>
          <ul className="rule-list">
            {rules.length === 0 && <li className="muted">Мало данных для правил</li>}
            {rules.slice(0, 5).map((r) => (
              <li key={`${r.input}-${r.top1_action}`}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Signature kind="action" />
                  <span className="mono">{r.top1_action}</span>
                </div>
                <div className="muted">
                  после «{r.input}» → {(r.top1_mass * 100).toFixed(0)}% (n={r.support})
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {role && !agent && (
        <div>
          <div className="rf-level">подразделение</div>
          <div style={{ fontSize: 21 }}>{roleTitle(role.id, model.donor_id)}</div>
          <p className="muted">{roleWhat(role.id, model.donor_id)}</p>
          <div className="inspect-actions">
            <button type="button" className="btn" onClick={() => onExcludeRole?.(role.id)}>
              Вычеркнуть подразделение
            </button>
            <button type="button" className="btn ghost" onClick={() => onBoostRole?.(role.id)}>
              Нагрузка ×2 только здесь
            </button>
          </div>
        </div>
      )}

      <details className="legend-details">
        <summary>Легенда значков</summary>
        <Legend />
      </details>
    </aside>
  );
}
