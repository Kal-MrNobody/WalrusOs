const BASE = process.env.NEXT_PUBLIC_BRIDGE_URL ?? "http://localhost:8787";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export function wsUrl(): string {
  return BASE.replace(/^http/, "ws") + "/ws/events";
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Stats {
  agents: number;
  streams: number;
  events: number;
  blobs: number;
  sui_anchors: number;
}

export interface ActivityEvent {
  id: string;
  event_type: string;
  agent_id: string;
  agent_name: string;
  framework?: string;
  workspace_id: string;
  stream_id: string;
  blob_id: string;
  timestamp: string;
  tx_digest: string;
}

export interface Agent {
  id: string;
  name: string;
  workspace_id: string;
  status: "active" | "paused" | "terminated" | string;
  execution_counter: number;
  memory_counter: number;
  artifact_counter: number;
  public_key: string;
  trust_root: string;
  sui_object_id: string | null;
  created_at: string;
}

export interface AgentReputation {
  successful_signatures: number;
  failed_verifications: number;
  memory_writes: number;
  artifact_uploads: number;
  validation_approvals: number;
  validation_failures: number;
  capability_grants: number;
  capability_revocations: number;
}

export interface Workspace {
  id: string; name: string; agents: number; streams: number; created_at: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: "agent" | "stream";
  status?: string;
  event_count: number;
  execution_count?: number;
  public_key?: string;
  created_at?: string;
  sui_object_id?: string | null;
  head?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  count: number;
}

export interface MemoryEventItem {
  id: string;
  agent_id: string;
  agent_name: string;
  stream_id: string;
  memory_type: string;
  tags: string[];
  importance: number;
  summary: string;
  content: Record<string, unknown>;
  blob_id: string;
  event_hash: string;
  signature: string;
  public_key: string;
  verified: boolean;
  timestamp: string;
  tx_digest: string;
  workspace_id: string;
}

export interface Stream {
  id: string; name: string; events: number; workspace: string;
  head?: string; epoch?: number; created_at?: string; size_kb?: number;
}

export interface BlobExplorer {
  found: boolean;
  blob_id: string;
  size?: number;
  content?: Record<string, unknown> | string;
  walrus_url?: string;
  error?: string;
}

export interface SuiObjectExplorer {
  found: boolean;
  object_id: string;
  object_type?: string;
  owner?: string;
  version?: string;
  digest?: string;
  fields?: Record<string, unknown>;
  sui_explorer_url?: string;
  error?: string;
}

export interface Permission {
  id: string; agent: string; stream: string; verbs: string[];
  granted_at: string; valid_until: string;
  // Additive — populated by the bridge's /api/permissions endpoint
  capability_id?: string;
  agent_name?: string;
  stream_name?: string;
  bitmask?: number;
  valid_until_label?: string;
  sui_object_url?: string;
}

export interface SearchResult {
  id: string; stream: string; content: string; score: number; timestamp: string;
}

export interface Task {
  id: string;
  workspace_id: string;
  title: string;
  description: string;
  created_by: string;
  created_by_name: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  status: "pending" | "in_progress" | "review" | "done" | string;
  priority: number;
  tags: string[];
  notes: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface MemorySearchResult {
  id: string;
  score: number;
  text: string;
  stream_id: string;
  agent_id: string;
  agent_name: string;
  memory_type: string;
  timestamp: string;
  search_time_ms?: number;
}

export interface Snapshot {
  id: string;
  agent_id: string;
  agent_name: string;
  stream_id: string;
  summary: string;
  content: Record<string, unknown>;
  blob_id: string;
  timestamp: string;
  tags: string[];
}

export interface AgentPresence {
  session_id: string;
  agent_id: string;
  agent_name: string;
  workspace_id: string;
  framework: string;
  started_at: string;
  last_heartbeat: string;
  status: "online" | "thinking" | "working" | "idle" | "waiting" | "offline" | string;
  current_task_label: string | null;
  current_file: string | null;
  current_memory_query: string | null;
  memory_reads: number;
  memory_writes: number;
  artifacts_published: number;
  tasks_completed: number;
}

export interface AgentRegistration {
  agent_id: string;
  agent_name: string;
  framework: string;
  workspace_id: string;
  capabilities: Array<{ name: string; languages: string[]; description: string }>;
  tools_exposed: string[];
  max_concurrent_tasks: number;
}

export interface AppSettings {
  package_id: string;
  ledger_anchor_id: string;
  wallet: string;
  network: string;
  publisher_url: string;
  aggregator_url: string;
  db_path: string;
  mcp_status: string;
  claude_desktop_config: string;
  cursor_config: string;
  sui_explorer_package: string;
  sui_explorer_ledger: string;
}

// ── API Functions ─────────────────────────────────────────────────────────────

export const api = {
  stats: {
    get: () => apiFetch<Stats>("/api/stats"),
  },
  activity: {
    recent: (limit = 20) => apiFetch<ActivityEvent[]>(`/api/activity?limit=${limit}`),
  },
  workspaces: {
    list: () => apiFetch<Workspace[]>("/api/workspaces"),
    create: (name: string) => apiFetch<Workspace>("/api/workspaces", {
      method: "POST", body: JSON.stringify({ name }),
    }),
    sync: () => apiFetch<{ status: string; timestamp?: string; error?: string }>("/api/workspace/sync"),
  },
  agents: {
    listAll: () => apiFetch<Agent[]>("/api/agents"),
    listForWorkspace: (workspace: string) => apiFetch<Agent[]>(`/api/workspaces/${workspace}/agents`),
    get: (agentId: string) => apiFetch<Agent>(`/api/agents/${agentId}`),
    graph: (workspace: string) => apiFetch<GraphData>(`/api/workspaces/${workspace}/graph`),
  },
  graph: {
    get: () => apiFetch<GraphData>("/api/graph-data"),
  },
  streams: {
    list: () => apiFetch<Stream[]>("/api/streams"),
    timeline: (streamId: string) => apiFetch<MemoryEventItem[]>(`/api/streams/${streamId}/timeline`),
  },
  memory: {
    events: (params?: {
      stream?: string; agent?: string; memory_type?: string;
      limit?: number; offset?: number;
    }) => {
      const q = new URLSearchParams();
      if (params?.stream) q.set("stream", params.stream);
      if (params?.agent) q.set("agent", params.agent);
      if (params?.memory_type) q.set("memory_type", params.memory_type);
      if (params?.limit != null) q.set("limit", String(params.limit));
      if (params?.offset != null) q.set("offset", String(params.offset));
      return apiFetch<MemoryEventItem[]>(`/api/memory/events?${q}`);
    },
  },
  explorer: {
    blob: (blobId: string) => apiFetch<BlobExplorer>(`/api/explorer/blob/${blobId}`),
    object: (objectId: string) => apiFetch<SuiObjectExplorer>(`/api/explorer/object/${objectId}`),
  },
  artifacts: {
    list: () => apiFetch<Array<{
      id: string; name: string; type: string; stream: string;
      size_kb: number | null; created_at: string; blob_id: string;
    }>>("/api/artifacts"),
  },
  search: {
    query: (q: string) => apiFetch<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
    memory: (q: string, limit = 20) =>
      apiFetch<MemorySearchResult[]>(`/api/memory/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  },
  permissions: {
    list: () => apiFetch<Permission[]>("/api/permissions"),
    delegate: (body: Partial<Permission>) => apiFetch<Permission>("/api/permissions", {
      method: "POST", body: JSON.stringify(body),
    }),
    revoke: (id: string) => apiFetch<{ status: string }>(`/api/permissions/${id}`, { method: "DELETE" }),
  },
  tasks: {
    list: () => apiFetch<Task[]>("/api/tasks"),
    create: (body: Partial<Task>) => apiFetch<{ id: string; title: string; status: string }>("/api/tasks", {
      method: "POST", body: JSON.stringify(body),
    }),
    updateStatus: (id: string, status: string) =>
      apiFetch<{ id: string; status: string }>(`/api/tasks/${id}/status`, {
        method: "POST", body: JSON.stringify({ status }),
      }),
  },
  snapshots: {
    list: (limit = 50) => apiFetch<Snapshot[]>(`/api/snapshots?limit=${limit}`),
  },
  settings: {
    get: () => apiFetch<AppSettings>("/api/settings"),
  },
  presence: {
    list: () => apiFetch<AgentPresence[]>("/agent/presence"),
  },
  registry: {
    list: () => apiFetch<AgentRegistration[]>("/agent/registry"),
    discover: (params?: { capability?: string; framework?: string }) => {
      const q = new URLSearchParams();
      if (params?.capability) q.set("capability", params.capability);
      if (params?.framework)  q.set("framework",  params.framework);
      return apiFetch<AgentRegistration[]>(`/agent/discover?${q}`);
    },
  },
};
