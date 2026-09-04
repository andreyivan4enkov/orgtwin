import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { OrgModel, QueueSlice } from "../lib/api";
import { queuePressureMap } from "../lib/layout";
import {
  agentTitle,
  donorOrgMeta,
  roleTitle,
  roleWhat,
} from "../lib/orgLabels";
import { STRUCTURE_VIEWS, type StructureView } from "../lib/biViews";
import { HierarchyBoard } from "./HierarchyBoard";
import { MarkovBlanket } from "./MarkovBlanket";

/** Аудит: переключение Иерархия | Покрывало (стандарт BI: не смешивать). */
export function AuditStage({
  model,
  selectedId,
  onSelect,
  queueSlice,
}: {
  model: OrgModel;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  queueSlice?: QueueSlice | null;
}) {
  const [view, setView] = useState<StructureView>("hierarchy");
  const meta = donorOrgMeta(model.donor_id);
  const pressure = useMemo(() => queuePressureMap(queueSlice), [queueSlice]);
  const spec = STRUCTURE_VIEWS.find((v) => v.id === view)!;

  const selectedAgent = model.agents.find((a) => a.id === selectedId);
  const needsPick = view === "blanket" && !selectedAgent;

  const histRef = useRef<{ stack: string[]; idx: number }>({ stack: [], idx: -1 });
  const skipHistPush = useRef(false);
  const [histUi, setHistUi] = useState({
    canBack: false,
    canForward: false,
    trail: [] as string[],
  });

  const publishHist = useCallback((stack: string[], idx: number) => {
    histRef.current = { stack, idx };
    const next = {
      canBack: idx > 0,
      canForward: idx >= 0 && idx < stack.length - 1,
      trail: stack.slice(Math.max(0, idx - 3), idx + 1),
    };
    setHistUi((prev) => {
      if (
        prev.canBack === next.canBack &&
        prev.canForward === next.canForward &&
        prev.trail.length === next.trail.length &&
        prev.trail.every((t, i) => t === next.trail[i])
      ) {
        return prev;
      }
      return next;
    });
  }, []);

  useEffect(() => {
    if (view !== "blanket") {
      publishHist([], -1);
      skipHistPush.current = false;
    }
  }, [view, publishHist]);

  useEffect(() => {
    if (view !== "blanket" || !selectedAgent) return;
    if (skipHistPush.current) {
      skipHistPush.current = false;
      return;
    }
    const { stack, idx } = histRef.current;
    if (stack[idx] === selectedAgent.id) return;
    const base = stack.slice(0, idx + 1);
    const next =
      base.length && base[base.length - 1] === selectedAgent.id
        ? base
        : [...base, selectedAgent.id];
    publishHist(next, next.length - 1);
  }, [view, selectedAgent?.id, publishHist, selectedAgent]);

  const goHist = useCallback(
    (dir: -1 | 1) => {
      const { stack, idx } = histRef.current;
      const ni = idx + dir;
      if (ni < 0 || ni >= stack.length) return;
      skipHistPush.current = true;
      publishHist(stack, ni);
      onSelect(stack[ni]);
    },
    [onSelect, publishHist]
  );

  const drillSelect = useCallback(
    (id: string) => {
      const { stack, idx } = histRef.current;
      const base = stack.slice(0, idx + 1);
      const next = base.length && base[base.length - 1] === id ? base : [...base, id];
      publishHist(next, next.length - 1);
      skipHistPush.current = true;
      onSelect(id);
    },
    [onSelect, publishHist]
  );

  return (
    <div className="audit-stage">
      <div className="audit-toolbar">
        <div className="segment" role="group" aria-label="Вид структуры">
          {STRUCTURE_VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              className={view === v.id ? "active" : ""}
              title={v.how}
              onClick={() => setView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
        {view === "blanket" && selectedAgent && (
          <div className="blanket-nav" role="navigation" aria-label="История покрывала">
            <button
              type="button"
              className="btn ghost icon-btn"
              disabled={!histUi.canBack}
              title="Назад к предыдущему сотруднику"
              aria-label="Назад"
              onClick={() => goHist(-1)}
            >
              ←
            </button>
            <button
              type="button"
              className="btn ghost icon-btn"
              disabled={!histUi.canForward}
              title="Вперёд"
              aria-label="Вперёд"
              onClick={() => goHist(1)}
            >
              →
            </button>
            {histUi.trail.length > 0 && (
              <span className="blanket-trail muted" title="Путь по покрывалам">
                {histUi.trail.map((id, i) => (
                  <span key={`${id}-${i}`}>
                    {i > 0 && " → "}
                    <button
                      type="button"
                      className={`linkish trail-link${id === selectedAgent.id ? " current" : ""}`}
                      onClick={() => {
                        const { stack } = histRef.current;
                        const jump = stack.lastIndexOf(id);
                        if (jump < 0) return;
                        skipHistPush.current = true;
                        publishHist(stack, jump);
                        onSelect(id);
                      }}
                    >
                      {agentTitle(id, model.donor_id)}
                    </button>
                  </span>
                ))}
              </span>
            )}
          </div>
        )}
        <div className="audit-question">
          <strong>Вопрос сцены:</strong> {spec.question}
        </div>
        <details className="audit-meta">
          <summary>Как читать</summary>
          <p>{spec.how}</p>
          <p className="muted">{meta.structureNote}</p>
        </details>
      </div>

      {needsPick ? (
        <div className="audit-empty">
          <h3>Выберите сотрудника</h3>
          <p className="muted">
            Вид «Покрывало» показывает только окрестность одного человека: кто передаёт
            ему дела, кому он передаёт, и коллег в подразделении. Выберите сотрудника
            слева или переключитесь на «Иерархию».
          </p>
          <ul className="audit-pick-list">
            {[...model.agents]
              .sort((a, b) => b.n_events - a.n_events)
              .slice(0, 12)
              .map((a) => (
                <li key={a.id}>
                  <button type="button" className="btn ghost" onClick={() => onSelect(a.id)}>
                    {agentTitle(a.id, model.donor_id)}
                    <span className="muted">
                      {" "}
                      · {roleTitle(a.role_id, model.donor_id)}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
        </div>
      ) : view === "hierarchy" ? (
        <HierarchyBoard
          model={model}
          selectedId={selectedId}
          onSelect={onSelect}
          pressure={pressure}
        />
      ) : (
        <MarkovBlanket
          model={model}
          focusId={selectedAgent!.id}
          onSelect={drillSelect}
          pressure={pressure}
        />
      )}

      {selectedAgent && view === "hierarchy" && (
        <div className="audit-footer muted">
          Выбран: {agentTitle(selectedAgent.id, model.donor_id)} ·{" "}
          {roleTitle(selectedAgent.role_id, model.donor_id)} (
          {roleWhat(selectedAgent.role_id, model.donor_id)})
        </div>
      )}
    </div>
  );
}
