"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Layers, Database, Clock, ChevronRight, GitBranch } from "lucide-react";
import { api } from "@/lib/api";
import type { Stream } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";

function relativeTime(ts?: string) {
  if (!ts) return "—";
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

function StreamCard({ stream }: { stream: Stream }) {
  return (
    <Link
      href={`/memory/timeline?stream=${stream.id}`}
      className="group flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900/50
                 p-4 hover:border-violet-600/40 hover:bg-slate-800/50 transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-900/40 border border-violet-800/40">
            <GitBranch className="h-4 w-4 text-violet-400" />
          </div>
          <div className="min-w-0">
            <p className="font-medium text-slate-200 truncate">{stream.name || "Unnamed Stream"}</p>
            <p className="text-[11px] text-slate-600 font-mono truncate">{stream.id.slice(0, 20)}…</p>
          </div>
        </div>
        <ChevronRight className="h-4 w-4 text-slate-700 group-hover:text-violet-400 shrink-0 transition-colors mt-1" />
      </div>

      <div className="grid grid-cols-3 gap-3 border-t border-slate-800 pt-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600 font-medium">Events</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-200">
            {(stream.events ?? 0).toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600 font-medium">Size</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-200">
            {stream.size_kb != null ? `${stream.size_kb.toFixed(1)} KB` : "—"}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600 font-medium">Updated</p>
          <p className="mt-0.5 text-sm text-slate-400">{relativeTime(stream.created_at)}</p>
        </div>
      </div>

      {stream.head && (
        <div className="flex items-center gap-2 rounded-lg bg-slate-950/60 px-2.5 py-1.5">
          <Database className="h-3 w-3 text-slate-600 shrink-0" />
          <span className="text-[11px] text-slate-600">Head blob:</span>
          <TruncatedId value={stream.head} chars={12} />
        </div>
      )}
    </Link>
  );
}

export default function StreamsPage() {
  const [streams, setStreams] = useState<Stream[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    api.streams.list()
      .then(setStreams)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Layers className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Streams</h1>
          <p className="text-sm text-slate-500">
            {loading ? "Loading…" : `${streams.length} stream${streams.length !== 1 ? "s" : ""} · click to view memory timeline`}
          </p>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          {error} — <button onClick={() => window.location.reload()} className="underline">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
          ))}
        </div>
      ) : streams.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Layers className="h-10 w-10 text-slate-700" />
          <p className="text-sm text-slate-600">No streams found.</p>
          <p className="text-xs text-slate-700">
            Create one with <code className="bg-slate-800 px-1 rounded">agent.memory_stream("name")</code>
          </p>
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {streams.map(s => <StreamCard key={s.id} stream={s} />)}
        </div>
      )}
    </div>
  );
}
