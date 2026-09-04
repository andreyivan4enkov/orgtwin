import { useEffect, useState } from "react";
import { api, type SnapshotInfo } from "../lib/api";

export function SnapshotPanel({
  donorId,
  hasModel,
  onLoaded,
}: {
  donorId: string;
  hasModel: boolean;
  onLoaded: (model: unknown) => void;
}) {
  const [items, setItems] = useState<SnapshotInfo[]>([]);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () => {
    void api.listSnapshots(donorId).then((r) => setItems(r.items)).catch(() => setItems([]));
  };

  useEffect(() => {
    refresh();
  }, [donorId]);

  async function save() {
    const n = name.trim() || `снимок_${new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-")}`;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.saveSnapshot(donorId, n);
      setMsg(`Сохранено: ${r.name}`);
      setName("");
      refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function load(n: string) {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.loadSnapshot(donorId, n);
      onLoaded(r.model);
      setMsg(`Загружен снимок «${n}»`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(n: string) {
    setBusy(true);
    try {
      await api.deleteSnapshot(donorId, n);
      refresh();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="snapshot-panel" open>
      <summary>Сохранённые модели</summary>
      <div className="snapshot-save">
        <input
          className="donor-select"
          placeholder="Имя снимка"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={busy || !hasModel}
        />
        <button
          type="button"
          className="btn icon-btn"
          disabled={busy || !hasModel}
          onClick={() => void save()}
          title="Сохранить снимок модели"
          aria-label="Сохранить снимок модели"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none">
            <path
              d="M3 2.5h8.2L13.5 4.8V13a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5V3A.5.5 0 0 1 3 2.5Z"
              stroke="currentColor"
              strokeWidth="1.4"
            />
            <path d="M5 2.5v3.5h5.5V2.5" stroke="currentColor" strokeWidth="1.4" />
            <rect x="5" y="9" width="6" height="3.5" rx="0.4" stroke="currentColor" strokeWidth="1.4" />
          </svg>
        </button>
      </div>
      <ul className="rail-list">
        {items.length === 0 && <li className="muted">Пока нет снимков</li>}
        {items.map((it) => (
          <li key={it.name} className="rail-item snapshot-row">
            <button type="button" className="linkish" disabled={busy} onClick={() => void load(it.name)}>
              {it.name}
              <span className="muted" style={{ display: "block", fontSize: 11 }}>
                {it.saved_at?.slice(0, 19) || ""} · {it.n_agents} агентов
                {it.has_queue ? " · очереди" : ""}
              </span>
            </button>
            <button type="button" className="btn ghost" disabled={busy} onClick={() => void remove(it.name)}>
              ×
            </button>
          </li>
        ))}
      </ul>
      {msg && <p className="muted" style={{ fontSize: 12 }}>{msg}</p>}
    </details>
  );
}
