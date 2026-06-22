"use client";

import { useEffect, useState } from "react";
import { Bookmark, Plus, Database, Tag, User, Calendar } from "lucide-react";
import { api } from "@/lib/api";
import type { Snapshot } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

function formatDate(ts: string) {
  return new Date(ts).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function dateKey(ts: string) {
  return new Date(ts).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function SnapshotCard({ snap }: { snap: Snapshot }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 hover:border-slate-700 transition-colors overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full text-left p-4"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-900/30 border border-amber-800/40 mt-0.5">
              <Bookmark className="h-4 w-4 text-amber-400" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-200 leading-snug line-clamp-2">
                {snap.summary || "Checkpoint"}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600">
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" /> {snap.agent_name}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" /> {formatDate(snap.timestamp)}
                </span>
              </div>
            </div>
          </div>
          <span className="shrink-0 text-slate-600 text-xs mt-1">{expanded ? "▲" : "▼"}</span>
        </div>

        {(snap.tags ?? []).length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5 pl-11">
            {snap.tags.map(t => (
              <span key={t} className="flex items-center gap-0.5 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                <Tag className="h-2.5 w-2.5" /> {t}
              </span>
            ))}
          </div>
        )}
      </button>

      {expanded && (
        <div className="border-t border-slate-800 px-4 pb-4 pt-3 space-y-3">
          {/* Content fields */}
          {Object.keys(snap.content ?? {}).length > 0 && (
            <div className="rounded-lg bg-slate-950/60 p-3 text-xs font-mono text-slate-400 space-y-1 overflow-x-auto max-h-40">
              {Object.entries(snap.content).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-violet-400 shrink-0">{k}:</span>
                  <span className="text-slate-300 break-all">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-slate-600 mb-1">Blob ID</p>
              <TruncatedId value={snap.blob_id} chars={14} />
            </div>
            <div>
              <p className="text-slate-600 mb-1">Stream ID</p>
              <TruncatedId value={snap.stream_id} chars={14} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SnapshotsPage() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [creating, setCreating]   = useState(false);

  useEffect(() => {
    api.snapshots.list()
      .then(setSnapshots)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Group by date
  const grouped: { date: string; items: Snapshot[] }[] = [];
  const seen = new Map<string, Snapshot[]>();
  for (const s of snapshots) {
    const dk = dateKey(s.timestamp);
    if (!seen.has(dk)) { seen.set(dk, []); grouped.push({ date: dk, items: seen.get(dk)! }); }
    seen.get(dk)!.push(s);
  }

  async function createCheckpoint() {
    setCreating(true);
    try {
      await api.search.memory("checkpoint summary");
      alert("Checkpoint creation is triggered from the Python runtime via agent.summarize(). Use the CLI or SDK to create checkpoints.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <Bookmark className="h-6 w-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Snapshots</h1>
            <p className="text-sm text-slate-500">
              {loading ? "Loading…" : `${snapshots.length} checkpoint${snapshots.length !== 1 ? "s" : ""}`}
            </p>
          </div>
        </div>
        <button
          onClick={createCheckpoint}
          disabled={creating}
          className="flex items-center gap-1.5 rounded-lg border border-violet-700/50 bg-violet-900/20
                     px-3 py-2 text-sm text-violet-300 hover:bg-violet-900/40 transition-colors disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" /> Create Checkpoint
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {loading ? (
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
          ))}
        </div>
      ) : snapshots.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Bookmark className="h-10 w-10 text-slate-700" />
          <p className="text-sm text-slate-600">No snapshots yet.</p>
          <p className="text-xs text-slate-700">
            Create one with <code className="bg-slate-800 rounded px-1">await agent.summarize(stream)</code>
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(({ date, items }) => (
            <div key={date}>
              <div className="flex items-center gap-3 mb-3">
                <div className="h-px flex-1 bg-slate-800" />
                <span className="text-xs text-slate-600 font-medium">{date}</span>
                <div className="h-px flex-1 bg-slate-800" />
              </div>
              <div className="space-y-3">
                {items.map(s => <SnapshotCard key={s.id} snap={s} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
