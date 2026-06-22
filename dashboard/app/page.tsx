"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Users, GitBranch, Zap, Database, Hash,
  ExternalLink, RefreshCw, Plus, X, Radio,
} from "lucide-react";
import { api, wsUrl } from "@/lib/api";
import type { Stats, ActivityEvent, AgentPresence } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(ts: string): string {
  if (!ts) return "";
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function eventVerb(eventType: string): { verb: string; color: string } {
  if (eventType === "AgentRegistered")  return { verb: "registered",        color: "bg-blue-500" };
  if (eventType === "MemoryAppended")   return { verb: "published to",      color: "bg-violet-500" };
  if (eventType === "WorkspaceCreated") return { verb: "created workspace", color: "bg-emerald-500" };
  if (eventType === "AgentPaused")      return { verb: "paused",            color: "bg-amber-500" };
  if (eventType === "AgentTerminated")  return { verb: "terminated",        color: "bg-red-500" };
  return {
    verb: eventType.toLowerCase().replace(/([A-Z])/g, " $1").trim(),
    color: "bg-slate-500",
  };
}

function presenceStatusDot(status: string) {
  const color =
    status === "online"   ? "bg-emerald-400" :
    status === "thinking" ? "bg-amber-400"   :
    status === "working"  ? "bg-blue-400"    :
    status === "idle"     ? "bg-slate-500"   :
    status === "waiting"  ? "bg-orange-400"  :
    status === "offline"  ? "bg-slate-700"   : "bg-slate-500";
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full shrink-0",
        color,
        status === "online" || status === "thinking" || status === "working"
          ? "ring-2 ring-current ring-offset-1 ring-offset-slate-900 opacity-90"
          : "",
      )}
    />
  );
}

const FRAMEWORK_BADGE: Record<string, string> = {
  "claude-code": "bg-violet-900/60 text-violet-300 border-violet-700",
  "cursor":      "bg-blue-900/60 text-blue-300 border-blue-700",
  "windsurf":    "bg-cyan-900/60 text-cyan-300 border-cyan-700",
  "gemini":      "bg-yellow-900/60 text-yellow-300 border-yellow-700",
  "antigravity": "bg-orange-900/60 text-orange-300 border-orange-700",
  "custom":      "bg-slate-800 text-slate-400 border-slate-700",
};

function frameworkBadge(framework: string) {
  const cls = FRAMEWORK_BADGE[framework] ?? FRAMEWORK_BADGE.custom;
  return (
    <span className={cn("text-[10px] font-medium rounded border px-1.5 py-0.5 shrink-0", cls)}>
      {framework}
    </span>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({
  label, value, icon: Icon, loading,
}: {
  label: string; value: number | null; icon: React.ComponentType<{ className?: string }>;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-widest text-slate-500">{label}</span>
        <Icon className="h-4 w-4 text-slate-600" />
      </div>
      {loading ? (
        <div className="h-8 w-20 animate-pulse rounded bg-slate-800" />
      ) : (
        <p className="text-3xl font-bold tabular-nums text-white">
          {value?.toLocaleString() ?? "—"}
        </p>
      )}
    </div>
  );
}

// ── Activity Row ──────────────────────────────────────────────────────────────

function ActivityRow({ event, isNew }: { event: ActivityEvent; isNew: boolean }) {
  const { verb, color } = eventVerb(event.event_type);
  const walrusUrl = event.blob_id
    ? `https://aggregator.walrus-testnet.walrus.space/v1/blobs/${event.blob_id}`
    : null;

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-300",
        isNew ? "bg-violet-500/10" : "hover:bg-slate-800/40"
      )}
    >
      <span className={cn("h-2 w-2 rounded-full shrink-0", color)} />

      <div className="min-w-0 flex-1 text-sm flex items-center gap-1.5 flex-wrap">
        <span className="font-semibold text-slate-200">
          {event.agent_name || "Unknown"}
        </span>
        {event.framework ? frameworkBadge(event.framework) : null}
        <span className="text-slate-500">{verb}</span>
        {event.stream_id ? (
          <span className="font-mono text-violet-400 text-xs">
            {event.stream_id.slice(0, 10)}…
          </span>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
        <span title={event.timestamp}>{relativeTime(event.timestamp)}</span>
        {walrusUrl && (
          <a
            href={walrusUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-slate-600 hover:text-violet-400 transition-colors"
            title={event.blob_id}
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>
    </div>
  );
}

// ── Connected Agent Card ──────────────────────────────────────────────────────

function AgentCard({ session }: { session: AgentPresence }) {
  return (
    <div className="flex items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-slate-800/40 transition-colors">
      <div className="mt-1.5">{presenceStatusDot(session.status)}</div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="truncate text-sm font-medium text-slate-200">
            {session.agent_name}
          </p>
          {frameworkBadge(session.framework)}
        </div>

        {/* Current activity hint */}
        {session.current_task_label && (
          <p className="truncate text-xs text-slate-500" title={session.current_task_label}>
            ⚡ {session.current_task_label}
          </p>
        )}
        {session.current_memory_query && !session.current_task_label && (
          <p className="truncate text-xs text-slate-500" title={session.current_memory_query}>
            🔍 {session.current_memory_query}
          </p>
        )}
        {!session.current_task_label && !session.current_memory_query && (
          <p className="text-xs text-slate-600">
            {session.status} · {session.memory_writes}w {session.memory_reads}r
          </p>
        )}
      </div>

      <div className="shrink-0 text-right">
        <p className="text-[10px] text-slate-600" title={session.last_heartbeat}>
          {relativeTime(session.last_heartbeat)}
        </p>
      </div>
    </div>
  );
}

// ── New Stream Modal ──────────────────────────────────────────────────────────

function NewStreamModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const create = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      await api.workspaces.create(name.trim());
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-80 rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-semibold text-slate-100">New Stream</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
            <X className="h-4 w-4" />
          </button>
        </div>
        <input
          autoFocus
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm
                     text-slate-100 placeholder-slate-600 outline-none focus:border-violet-500"
          placeholder="stream-name"
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => e.key === "Enter" && create()}
        />
        <button
          onClick={create}
          disabled={creating || !name.trim()}
          className="mt-3 w-full rounded-lg bg-violet-600 py-2 text-sm font-medium
                     text-white hover:bg-violet-500 disabled:opacity-50 transition-colors"
        >
          {creating ? "Creating…" : "Create"}
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const [stats, setStats]       = useState<Stats | null>(null);
  const [statsLoading, setSL]   = useState(true);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [presence, setPresence] = useState<AgentPresence[]>([]);
  const [newEventIds, setNew]   = useState<Set<string>>(new Set());
  const [syncing, setSyncing]   = useState(false);
  const [showModal, setModal]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Initial load
  useEffect(() => {
    Promise.all([
      api.stats.get(),
      api.activity.recent(20),
      api.presence.list(),
    ]).then(([s, act, pres]) => {
      setStats(s);
      setActivity(act);
      setPresence(pres);
    }).catch(e => setError(String(e))).finally(() => setSL(false));
  }, []);

  // WebSocket for live events + presence
  useEffect(() => {
    let active = true;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onmessage = (e) => {
        if (!active) return;
        try {
          const msg = JSON.parse(e.data) as Record<string, unknown>;
          const msgType = msg.type as string | undefined;

          // ── Presence snapshot (sent on connection) ────────────────────────
          // Bridge spreads {"type": "presence_snapshot", "agents": [...]}.
          if (msgType === "presence_snapshot") {
            const agents = (msg.agents ?? msg.sessions ?? []) as AgentPresence[];
            setPresence(agents);
            return;
          }

          // ── Presence events (heartbeat / join / leave) ────────────────────
          // Bridge spreads the session fields onto the message itself, so
          // msg.agent_id / msg.agent_name / msg.status are top-level.
          if (msgType === "agent_joined" || msgType === "agent_heartbeat") {
            const agentId = msg.agent_id as string | undefined;
            if (!agentId) return;
            // Reconstruct an AgentPresence-shaped object from the flat fields
            const { type: _t, ...rest } = msg;
            const session = rest as unknown as AgentPresence;
            setPresence(prev => {
              const idx = prev.findIndex(s => s.agent_id === agentId);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = { ...next[idx], ...session };
                return next;
              }
              return [session, ...prev];
            });
            // Heartbeats are NOT activity feed items — they're presence pings.
            // Intentionally do not push to the activity feed.
            return;
          }
          if (msgType === "agent_left") {
            const agentId = msg.agent_id as string | undefined;
            if (agentId) {
              setPresence(prev => prev.filter(s => s.agent_id !== agentId));
            }
            return;
          }

          // Legacy presence_update envelope — keep for compatibility
          if (msgType === "presence_update") {
            const evType = msg.event_type as string;
            if (evType === "agent_unregistered") {
              const agentId = msg.agent_id as string;
              setPresence(prev => prev.filter(s => s.agent_id !== agentId));
            } else {
              const session = msg.session as AgentPresence;
              if (session) {
                setPresence(prev => {
                  const idx = prev.findIndex(s => s.agent_id === session.agent_id);
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = session;
                    return next;
                  }
                  return [session, ...prev];
                });
              }
            }
            return;
          }

          // ── Memory event ──────────────────────────────────────────────────
          // Only treat messages with the memory.* type prefix as memory events,
          // so unrecognized presence-style messages can't fall through and
          // create "undefined…" rows in the activity feed.
          if (!msgType?.startsWith("memory.")) return;

          const raw = msg as unknown as {
            id: string; type: string; stream: string;
            agent: string; epoch: number; blob_id: string; timestamp: string;
          };
          const event: ActivityEvent = {
            id:           raw.id,
            event_type:   raw.type.replace("memory.", "MemoryAppended"),
            agent_id:     raw.agent,
            agent_name:   raw.agent ? raw.agent.slice(0, 8) + "…" : "Unknown",
            workspace_id: "",
            stream_id:    raw.stream,
            blob_id:      raw.blob_id,
            timestamp:    raw.timestamp,
            tx_digest:    "",
          };
          setActivity(prev => [event, ...prev].slice(0, 20));
          setNew(prev => { const s = new Set(prev); s.add(raw.id); return s; });
          // Refresh the full activity list so we pick up the proper agent_name
          // from the bridge (it joins against the agent table).
          api.activity.recent(20).then(setActivity).catch(() => {});
          api.stats.get().then(setStats).catch(() => {});
          setTimeout(() => setNew(p => { const s = new Set(p); s.delete(raw.id); return s; }), 3000);
        } catch {}
      };

      ws.onclose = () => {
        if (active) retryTimer = setTimeout(connect, 3000);
      };
    }

    connect();
    return () => {
      active = false;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try { await api.workspaces.sync(); } catch {}
    setSyncing(false);
    api.stats.get().then(setStats).catch(() => {});
    api.activity.recent(20).then(setActivity).catch(() => {});
    api.presence.list().then(setPresence).catch(() => {});
  };

  const onlineCount = presence.filter(s => s.status !== "offline").length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Overview</h1>
          <p className="mt-0.5 text-sm text-slate-500">WalrusOS — Persistent Memory Runtime</p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          Bridge unreachable: {error} —{" "}
          <button onClick={() => window.location.reload()} className="underline">Retry</button>
        </div>
      )}

      {/* ── Stat cards ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-5 gap-3">
        <StatCard label="Total Agents"   value={stats?.agents ?? null}      icon={Users}     loading={statsLoading} />
        <StatCard label="Active Streams" value={stats?.streams ?? null}     icon={GitBranch} loading={statsLoading} />
        <StatCard label="Total Events"   value={stats?.events ?? null}      icon={Zap}       loading={statsLoading} />
        <StatCard label="Walrus Blobs"   value={stats?.blobs ?? null}       icon={Database}  loading={statsLoading} />
        <StatCard label="Sui Anchors"    value={stats?.sui_anchors ?? null} icon={Hash}      loading={statsLoading} />
      </div>

      {/* ── Main content: feed left + presence right ─────────────────────── */}
      <div className="flex gap-5">

        {/* Activity Feed — 60% */}
        <div className="min-w-0 flex-[3]">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Live Activity</h2>
            <span className="text-xs text-slate-600">
              {activity.length} event{activity.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/40">
            {activity.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-600">
                <Zap className="mb-3 h-8 w-8 opacity-30" />
                <p className="text-sm">No activity yet — publish a memory to see it appear here</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-800/60 px-2 py-2">
                {activity.map(ev => (
                  <ActivityRow key={ev.id} event={ev} isNew={newEventIds.has(ev.id)} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Connected Agents (live presence) — 40% */}
        <div className="w-72 shrink-0">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-300">Connected Agents</h2>
              {onlineCount > 0 && (
                <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                  <Radio className="h-3 w-3 animate-pulse" />
                  live
                </span>
              )}
            </div>
            <span className="text-xs text-slate-600">{onlineCount} online</span>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/40">
            {presence.length === 0 ? (
              <div className="py-10 text-center">
                <Radio className="mx-auto mb-2 h-6 w-6 text-slate-700" />
                <p className="text-sm text-slate-600">No agents connected</p>
                <p className="mt-1 text-xs text-slate-700">
                  Call <code className="font-mono">agent.go_online()</code>
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate-800/60 px-1 py-1">
                {presence.map(session => (
                  <AgentCard key={session.agent_id} session={session} />
                ))}
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-600">
              Quick Actions
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={handleSync}
                disabled={syncing}
                className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800
                           px-3 py-2 text-sm text-slate-300 transition-colors
                           hover:border-violet-600/50 hover:bg-violet-600/10 hover:text-violet-300
                           disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
                {syncing ? "Syncing…" : "Sync Workspace"}
              </button>
              <button
                onClick={() => setModal(true)}
                className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800
                           px-3 py-2 text-sm text-slate-300 transition-colors
                           hover:border-violet-600/50 hover:bg-violet-600/10 hover:text-violet-300"
              >
                <Plus className="h-3.5 w-3.5" />
                New Stream
              </button>
            </div>
          </div>
        </div>
      </div>

      {showModal && <NewStreamModal onClose={() => setModal(false)} />}
    </div>
  );
}
