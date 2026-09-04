import { useState } from "react";
import { api } from "../lib/api";

export function UploadPanel({
  onUploaded,
}: {
  onUploaded: (donorId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await api.uploadDonor(file, {
        label: file.name,
      });
      setMsg(
        `Загружено: ${res.donor.label} · событий ${res.ingest?.n_events ?? "—"} · next-step ${
          res.metrics?.next_step != null ? `${(res.metrics.next_step * 100).toFixed(1)}%` : "—"
        }`
      );
      onUploaded(res.donor.id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload-inline">
      <label className="btn ghost" style={{ cursor: "pointer" }}>
        {busy ? "Загрузка…" : "Свой CSV/XES"}
        <input
          type="file"
          accept=".xes,.gz,.csv,.xes.gz"
          hidden
          disabled={busy}
          onChange={(e) => void onFile(e.target.files?.[0] || null)}
        />
      </label>
      {msg && <p className="muted upload-msg">{msg}</p>}
      {err && <p className="danger-text upload-msg">{err}</p>}
    </div>
  );
}
