export type Mode = "audit" | "flow" | "stress" | "design";

export interface DonorInfo {
  id: string;
  label: string;
  available: boolean;
  agent_column: string;
  role_mode: string;
  origin?: string;
  kind?: "demo" | "project";
  demo?: boolean;
  badge?: string;
  subtitle?: string;
  assumption?: boolean;
  format?: string;
}

export interface Agent {
  id: string;
  role_id: string;
  n_events: number;
  stuck_frac: number | null;
  exclusive_actions: { action: string; share: number; agent_n: number }[];
  capacity: number;
  origin: "log" | "manual" | "hybrid";
  n_distinct_actions?: number;
  mean_H_bits?: number | null;
}

export interface Role {
  id: string;
  label: string;
  n_agents: number;
  origin?: string;
}

export interface Rule {
  agent_id: string;
  input: string;
  top1_action: string;
  top1_mass: number;
  support: number;
}

export interface Edge {
  from_agent: string;
  to_agent: string;
  weight: number;
  origin?: string;
}

export interface QueueSlice {
  max_queue_any_real: number;
  bottleneck_agent: string | null;
  top_agents: { id: string; max_queue: number }[];
  boosted_agent?: string | null;
  boosted_queue_before?: number | null;
  boosted_queue_after?: number | null;
  n_events?: number;
  n_cases?: number;
  case_duration?: {
    p50_sec: number | null;
    p90_sec: number | null;
    mean_sec: number | null;
    n: number;
  };
  sla?: {
    sla_hours: number;
    breach_frac: number | null;
    p50_hours?: number | null;
    p90_hours?: number | null;
  };
}

export interface OrgModel {
  donor_id: string;
  label: string;
  origin: string;
  roles: Role[];
  agents: Agent[];
  rules: Rule[];
  edges: Edge[];
  metrics?: {
    next_step: number | null;
    top3: number | null;
    ce: number | null;
    n: number;
    policy_kind?: string | null;
  };
  queue_slices?: {
    x1: QueueSlice;
    x2: QueueSlice;
    x2_plus1: QueueSlice;
  } | null;
  flow_sample?: { case_id: string; agents: string[]; activities: string[] }[];
  honesty?: { proven: string[]; not_proven: string[] };
  build_wall_sec?: number;
  split_meta?: Record<string, unknown>;
  ingest?: {
    n_events: number;
    n_cases: number;
    n_agents: number;
    unknown_frac: number;
    span_days: number;
  };
  assumption?: boolean;
}

export interface DesignState {
  roles: { id: string; label?: string }[];
  agents: { id: string; role_id?: string; capacity?: number; n_events?: number }[];
  edges: { from_agent: string; to_agent: string; weight?: number }[];
  capacities: Record<string, number>;
}

export interface WhatIfResult {
  donor_id: string;
  exclude_agents: string[];
  exclude_roles: string[];
  role_multipliers: Record<string, number>;
  global_multiplier: number;
  baseline: QueueSlice;
  scenario: QueueSlice;
  delta_max_queue: number;
}

const base = "";

function authHeaders(): HeadersInit {
  const key = sessionStorage.getItem("orgtwin_api_key");
  return key ? { "X-API-Key": key } : {};
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${url}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  donors: () => json<DonorInfo[]>("/api/donors"),
  orgModel: (id: string, opts?: { force?: boolean; with_queue?: boolean }) => {
    const q = new URLSearchParams();
    if (opts?.force) q.set("force", "true");
    if (opts?.with_queue === false) q.set("with_queue", "false");
    const qs = q.toString();
    return json<OrgModel>(`/api/org-model/${id}${qs ? `?${qs}` : ""}`);
  },
  getDesign: (id: string) => json<DesignState>(`/api/design/${id}`),
  putDesign: (id: string, body: DesignState) =>
    json<DesignState>(`/api/design/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  whatIf: (
    id: string,
    body: {
      exclude_agents: string[];
      exclude_roles: string[];
      role_multipliers: Record<string, number>;
      global_multiplier: number;
    }
  ) =>
    json<WhatIfResult>(`/api/whatif/${id}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  uploadDonor: async (
    file: File,
    opts?: { donor_id?: string; label?: string; agent_column?: string; role_mode?: string }
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts?.donor_id) fd.append("donor_id", opts.donor_id);
    if (opts?.label) fd.append("label", opts.label);
    if (opts?.agent_column) fd.append("agent_column", opts.agent_column);
    if (opts?.role_mode) fd.append("role_mode", opts.role_mode);
    const res = await fetch(`${base}/api/donors/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<{
      donor: { id: string; label: string };
      ingest?: OrgModel["ingest"];
      metrics?: OrgModel["metrics"];
    }>;
  },
  greenfield: (body: { id?: string; template?: string; label?: string; n_cases?: number }) =>
    json<{ donor: { id: string } }>("/api/donors/greenfield", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  membranePrune: (
    id: string,
    body: { min_support?: number; apply?: boolean; edge_min_weight?: number }
  ) =>
    json<Record<string, unknown>>(`/api/membrane/${id}/prune`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  optimize: (id: string, body?: { apply_best?: boolean; weights?: Record<string, number> }) =>
    json<Record<string, unknown>>(`/api/optimize/${id}`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    }),
  cascade: (id: string, body: { exclude_agents: string[] }) =>
    json<Record<string, unknown>>(`/api/cascade/${id}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  putShifts: (id: string, body: { windows: Record<string, unknown>; use_default_office?: boolean }) =>
    json<Record<string, unknown>>(`/api/shifts/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  saveScenario: (id: string, name: string, payload: Record<string, unknown>) =>
    json(`/api/scenarios/${id}`, {
      method: "POST",
      body: JSON.stringify({ name, payload }),
    }),
  startBuild: (id: string, opts?: { force?: boolean; with_queue?: boolean }) =>
    json<{ job_id: string }>(`/api/org-model/${id}/build`, {
      method: "POST",
      body: JSON.stringify({
        force: opts?.force ?? false,
        with_queue: opts?.with_queue ?? true,
      }),
    }),
  buildStatus: (jobId: string) =>
    json<{
      job_id: string;
      donor_id: string;
      status: string;
      pct: number;
      stage: string;
      detail: string;
      error?: string | null;
      model?: OrgModel;
    }>(`/api/build/${jobId}`),
  listSnapshots: (id: string) =>
    json<{ donor_id: string; items: SnapshotInfo[] }>(`/api/snapshots/${id}`),
  saveSnapshot: (id: string, name: string, note = "") =>
    json<{ name: string; saved_at: string }>(`/api/snapshots/${id}`, {
      method: "POST",
      body: JSON.stringify({ name, note, with_queue: true }),
    }),
  loadSnapshot: (id: string, name: string) =>
    json<{ loaded: string; model: OrgModel }>(`/api/snapshots/${id}/load`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteSnapshot: (id: string, name: string) =>
    json(`/api/snapshots/${id}/${encodeURIComponent(name)}`, { method: "DELETE" }),
  arenaAttempt: (body: {
    donor_id: string;
    peak_after: number;
    exclude_agents?: string[];
    threshold?: number;
  }) =>
    json("/api/arena/attempt", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export interface SnapshotInfo {
  name: string;
  saved_at?: string;
  build_wall_sec?: number;
  n_agents?: number;
  has_queue?: boolean;
  note?: string;
}
