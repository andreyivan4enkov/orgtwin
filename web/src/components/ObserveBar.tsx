import type { SliceKey } from "../lib/layout";
import { SLICE_RU } from "../lib/labels";

export function ObserveBar({
  playing,
  onPlayingChange,
  slice,
  onSliceChange,
  hasQueue,
  hint,
}: {
  playing: boolean;
  onPlayingChange: (v: boolean) => void;
  slice: SliceKey;
  onSliceChange: (s: SliceKey) => void;
  hasQueue: boolean;
  hint?: string;
}) {
  return (
    <div className="observe-bar">
      <div className="observe-group">
        <span className="observe-label" title="Анимация потока и подсветка заторов на карте">
          Наблюдение
        </span>
        <button
          type="button"
          className={`btn observe-btn${playing ? " active" : ""}`}
          onClick={() => onPlayingChange(!playing)}
          title={playing ? "Пауза анимации" : "Запуск анимации потока и подсветки"}
        >
          {playing ? "Пауза" : "Пуск"}
        </button>
      </div>

      <div className="observe-group">
        <span className="observe-label" title="Сценарий входящего потока для очередей">
          Нагрузка
        </span>
        <div className="segment" role="group" aria-label="Срез нагрузки">
          {(Object.keys(SLICE_RU) as SliceKey[]).map((k) => (
            <button
              key={k}
              type="button"
              className={slice === k ? "active" : ""}
              title={SLICE_RU[k].hint}
              onClick={() => onSliceChange(k)}
              disabled={!hasQueue}
            >
              {SLICE_RU[k].short}
            </button>
          ))}
        </div>
      </div>

      {hint && <p className="observe-hint muted">{hint}</p>}
      {!hasQueue && (
        <p className="observe-hint muted">Срезы очереди ещё считаются или недоступны.</p>
      )}
    </div>
  );
}
