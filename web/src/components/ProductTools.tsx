import { useState } from "react";
import type { OrgModel } from "../lib/api";
import { api } from "../lib/api";

export function ProductTools({
  model,
  donorId,
  onRefresh,
}: {
  model: OrgModel;
  donorId: string;
  onRefresh: () => void;
}) {
  const [log, setLog] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      const r = await fn();
      setLog(`${label}: ${JSON.stringify(r).slice(0, 400)}…`);
      onRefresh();
    } catch (e) {
      setLog(`${label}: ошибка ${e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="product-tools">
      <summary>Инструменты продукта</summary>
      <div className="inspect-actions">
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() =>
            void run("Prune мембран", () =>
              api.membranePrune(donorId, { min_support: 30, apply: true, edge_min_weight: 0.05 })
            )
          }
        >
          Сузить мембраны
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() => void run("Оптимизатор", () => api.optimize(donorId, { apply_best: false }))}
        >
          Найти оптимум L
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() =>
            void run("Каскад", () => {
              const hot = model.agents.slice().sort((a, b) => (b.stuck_frac || 0) - (a.stuck_frac || 0))[0];
              return api.cascade(donorId, { exclude_agents: hot ? [hot.id] : [] });
            })
          }
        >
          Каскад отказа
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() =>
            void run("Смены 9–18", () => api.putShifts(donorId, { use_default_office: true, windows: {} }))
          }
        >
          Смены (допущение)
        </button>
        <a className="btn ghost" href={`/api/report/${donorId}`} target="_blank" rel="noreferrer">
          Отчёт директору
        </a>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() =>
            void run("Сохранить baseline", () =>
              api.saveScenario(donorId, "baseline", {
                metrics: model.metrics,
                queue: model.queue_slices?.x1,
              })
            )
          }
        >
          Сценарий baseline
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() =>
            void run("Greenfield кредит", () =>
              api.greenfield({ id: `GF_${Date.now().toString(36)}`, template: "credit" })
            )
          }
        >
          Greenfield из шаблона
        </button>
      </div>
      {model.assumption && <p className="badge manual">допущение (нет живого лога)</p>}
      {model.split_meta && (
        <p className="muted" style={{ fontSize: 12 }}>
          Split: fit/hold из журнала
          {model.ingest ? ` · событий ${model.ingest.n_events}, span ${model.ingest.span_days}д` : ""}
        </p>
      )}
      {model.queue_slices?.x1?.case_duration && (
        <p className="muted" style={{ fontSize: 12 }}>
          Σdt DES ×1: p50=
          {model.queue_slices.x1.case_duration.p50_sec != null
            ? `${(model.queue_slices.x1.case_duration.p50_sec / 3600).toFixed(1)}ч`
            : "—"}
          {model.queue_slices.x1.sla?.breach_frac != null &&
            ` · SLA breach ${(model.queue_slices.x1.sla.breach_frac * 100).toFixed(0)}%`}
        </p>
      )}
      {log && <pre className="mono" style={{ fontSize: 11, whiteSpace: "pre-wrap" }}>{log}</pre>}
    </details>
  );
}
