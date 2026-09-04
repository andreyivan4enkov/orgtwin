import type { OrgModel } from "../lib/api";
import { tokens } from "../lib/tokens";
import { agentTitle, agentWhat, donorOrgMeta, roleTitle, roleWhat } from "../lib/orgLabels";

/** Классическая оргсхема колонками (как org chart / decomposition tree). */
export function HierarchyBoard({
  model,
  selectedId,
  onSelect,
  pressure,
}: {
  model: OrgModel;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  pressure: Map<string, number>;
}) {
  const meta = donorOrgMeta(model.donor_id);
  const roles = model.roles.slice(0, 8);
  const byRole: Record<string, typeof model.agents> = {};
  for (const a of model.agents) {
    (byRole[a.role_id] ||= []).push(a);
  }
  for (const rid of Object.keys(byRole)) {
    byRole[rid].sort((a, b) => b.n_events - a.n_events);
  }

  return (
    <div className="hier-board">
      <button
        type="button"
        className="hier-org"
        onClick={() => onSelect(null)}
        title="Корень организации"
      >
        <span className="rf-level">организация</span>
        <span className="hier-org-title">{meta.company}</span>
      </button>

      <div className="hier-arrow" aria-hidden>
        ↓ подразделения
      </div>

      <div className="hier-cols">
        {roles.map((r) => {
          const people = (byRole[r.id] || []).slice(0, 10);
          const rest = (byRole[r.id] || []).length - people.length;
          const roleHot = people.some((a) => (pressure.get(a.id) || 0) >= 0.4);
          const roleCrit = people.some((a) => (pressure.get(a.id) || 0) >= 0.75);
          return (
            <section
              key={r.id}
              className={`hier-col${selectedId === r.id ? " selected" : ""}${
                roleCrit ? " critical" : roleHot ? " congested" : ""
              }`}
            >
              <header
                className="hier-col-head"
                onClick={() => onSelect(r.id)}
                title={roleWhat(r.id, model.donor_id)}
              >
                <span className="rf-level">подразделение</span>
                <strong>{roleTitle(r.id, model.donor_id)}</strong>
                <span className="muted">
                  {(byRole[r.id] || []).length} сотрудников · {roleWhat(r.id, model.donor_id)}
                </span>
              </header>
              <ul className="hier-people">
                {people.map((a) => {
                  const p = pressure.get(a.id) || 0;
                  return (
                    <li key={a.id}>
                      <button
                        type="button"
                        className={`hier-person${selectedId === a.id ? " selected" : ""}${
                          p >= 0.75 ? " critical" : p >= 0.4 ? " congested" : ""
                        }`}
                        onClick={() => onSelect(a.id)}
                        title={`${agentTitle(a.id, model.donor_id)}${
                          agentWhat(a.id, model.donor_id)
                            ? ` — ${agentWhat(a.id, model.donor_id)}`
                            : ""
                        } · ${a.n_events} событий в логе`}
                      >
                        <span
                          className="hier-dot"
                          style={{
                            borderColor:
                              p >= 0.75
                                ? tokens.colors.danger
                                : p >= 0.4
                                  ? tokens.colors.warn
                                  : tokens.colors.accent,
                          }}
                        />
                        <span className="hier-person-name">
                          {agentTitle(a.id, model.donor_id)}
                          {agentWhat(a.id, model.donor_id) && (
                            <span className="muted" style={{ display: "block", fontWeight: 400, fontSize: 12 }}>
                              {agentWhat(a.id, model.donor_id)}
                            </span>
                          )}
                        </span>
                        <span className="muted mono">{a.n_events}</span>
                      </button>
                    </li>
                  );
                })}
                {rest > 0 && (
                  <li className="muted" style={{ padding: "6px 10px" }}>
                    и ещё {rest}…
                  </li>
                )}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}
