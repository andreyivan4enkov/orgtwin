import { useCallback, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import type { ProblemExplain } from "../lib/problems";

/** Всплывающая карточка: перетаскивается, сворачивается, снова открывается. */
export function ProblemPopup({
  explain,
  onClose,
  onWhatIf,
  minimized,
  onToggleMinimize,
}: {
  explain: ProblemExplain;
  onClose: () => void;
  onWhatIf?: () => void;
  minimized?: boolean;
  onToggleMinimize?: () => void;
}) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ ox: number; oy: number; sx: number; sy: number } | null>(null);
  const moved = useRef(false);

  const onPointerDown = useCallback(
    (e: ReactMouseEvent) => {
      if ((e.target as HTMLElement).closest("button") && !minimized) return;
      e.preventDefault();
      moved.current = false;
      drag.current = { ox: e.clientX, oy: e.clientY, sx: pos.x, sy: pos.y };
      const onMove = (ev: MouseEvent) => {
        if (!drag.current) return;
        const dx = ev.clientX - drag.current.ox;
        const dy = ev.clientY - drag.current.oy;
        if (Math.abs(dx) + Math.abs(dy) > 4) moved.current = true;
        setPos({
          x: drag.current.sx + dx,
          y: drag.current.sy + dy,
        });
      };
      const onUp = () => {
        drag.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [pos.x, pos.y, minimized]
  );

  if (minimized) {
    return (
      <button
        type="button"
        className={`problem-chip ${explain.severity}`}
        style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
        onMouseDown={onPointerDown}
        onClick={() => {
          if (moved.current) return;
          onToggleMinimize?.();
        }}
        title="Открыть снова · можно перетащить"
      >
        ⚠ {explain.title}
      </button>
    );
  }

  return (
    <div
      className={`problem-popup ${explain.severity}`}
      role="dialog"
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
    >
      <div className="problem-popup-head drag-handle" onMouseDown={onPointerDown}>
        <strong title="Тяните за заголовок">{explain.title}</strong>
        <div className="problem-popup-actions">
          <button
            type="button"
            className="btn ghost"
            onClick={() => onToggleMinimize?.()}
            title="Свернуть в ярлык"
          >
            –
          </button>
          <button type="button" className="btn ghost" onClick={onClose} title="Закрыть">
            ✕
          </button>
        </div>
      </div>
      <section>
        <h4>Что это</h4>
        <p>{explain.meaning}</p>
      </section>
      <section>
        <h4>Что мешает</h4>
        <p>{explain.blocks}</p>
      </section>
      <section>
        <h4>Что сделать</h4>
        <ol>
          {explain.actions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ol>
      </section>
      {onWhatIf && (
        <button type="button" className="btn" onClick={onWhatIf}>
          Открыть сценарий «что если»
        </button>
      )}
    </div>
  );
}
