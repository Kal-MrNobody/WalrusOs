"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Users, ExternalLink, Network, ArrowUpDown, ChevronUp, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import type { Agent } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(ts: string) {
  if (!ts) return "—";
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

const STATUS_COLORS: Record<string, string> = {
  active:     "bg-emerald-900/50 text-emerald-400 border-emerald-800",
  paused:     "bg-amber-900/50 text-amber-400 border-amber-800",
  terminated: "bg-red-900/50 text-red-400 border-red-800",
};
const STATUS_DOT: Record<string, string> = {
  active: "bg-emerald-500", paused: "bg-amber-500", terminated: "bg-red-500",
};

type SortKey = "name" | "status" | "memory_counter" | "created_at";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [agents, setAgents]       = useState<Agent[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [filterStatus, setFilter] = useState<string>("");
  const [sortKey, setSortKey]     = useState<SortKey>("memory_counter");
  const [sortAsc, setSortAsc]     = useState(false);

  useEffect(() => {
    api.agents.listAll()
      .then(setAgents)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const sorted = useMemo(() => {
    let list = filterStatus ? agents.filter(a => a.status === filterStatus) : [...agents];
    list.sort((a, b) => {
      let av: string | number = a[sortKey] ?? "";
      let bv: string | number = b[sortKey] ?? "";
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      return sortAsc ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
    });
    return list;
  }, [agents, filterStatus, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(p => !p);
    else { setSortKey(key); setSortAsc(false); }
  };

  function SortBtn({ col }: { col: SortKey }) {
    const active = sortKey === col;
    return (
      <button onClick={() => toggleSort(col)} className="ml-1 inline-flex">
        {active
          ? (sortAsc ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)
          : <ArrowUpDown className="h-3 w-3 opacity-40" />}
      </button>
    );
  }

  const counts = useMemo(() => ({
    all:        agents.length,
    active:     agents.filter(a => a.status === "active").length,
    paused:     agents.filter(a => a.status === "paused").length,
    terminated: agents.filter(a => a.status === "terminated").length,
  }), [agents]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Agents</h1>
            <p className="text-sm text-slate-500">{agents.length} registered</p>
          </div>
        </div>
        <Link href="/agents/graph"
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800
                     px-3 py-2 text-sm text-slate-300 hover:border-violet-600/50 hover:text-violet-300 transition-colors">
          <Network className="h-3.5 w-3.5" /> View Graph
        </Link>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          {error} — <button onClick={() => window.location.reload()} className="underline">Retry</button>
        </div>
      )}

      {/* Status filter pills */}
      <div className="flex gap-2">
        {(["", "active", "paused", "terminated"] as const).map(s => (
          <button key={s}
            onClick={() => setFilter(s)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              filterStatus === s
                ? "border-violet-600 bg-violet-600/20 text-violet-300"
                : "border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-600"
            )}>
            {s === "" ? `All (${counts.all})` : `${s} (${counts[s]})`}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60">
              {[
                ["Name", "name"],
                ["Status", "status"],
                ["Events", "memory_counter"],
                ["Last Active", "created_at"],
                ["Trust Root", null],
                ["Actions", null],
              ].map(([label, key]) => (
                <th key={label as string}
                  className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {label}
                  {key && <SortBtn col={key as SortKey} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? [...Array(5)].map((_, i) => (
                <tr key={i} className="border-b border-slate-800/60">
                  {[...Array(6)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 w-24 animate-pulse rounded bg-slate-800" />
                    </td>
                  ))}
                </tr>
              ))
              : sorted.length === 0
                ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-slate-600">
                      No agents found
                    </td>
                  </tr>
                )
                : sorted.map(agent => {
                  const suiUrl = agent.sui_object_id
                    ? `https://suiexplorer.com/object/${agent.sui_object_id}?network=testnet`
                    : null;
                  return (
                    <tr key={agent.id}
                      className="border-b border-slate-800/40 hover:bg-slate-800/30 transition-colors">
                      {/* Name */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={cn("h-2 w-2 rounded-full shrink-0", STATUS_DOT[agent.status] ?? "bg-slate-500")} />
                          <span className="font-medium text-slate-200">{agent.name}</span>
                        </div>
                        <p className="mt-0.5 font-mono text-[10px] text-slate-600">
                          {agent.id.slice(0, 16)}…
                        </p>
                      </td>
                      {/* Status */}
                      <td className="px-4 py-3">
                        <span className={cn(
                          "rounded-full border px-2 py-0.5 text-[10px] font-medium",
                          STATUS_COLORS[agent.status] ?? "bg-slate-800 text-slate-400 border-slate-700"
                        )}>
                          {agent.status}
                        </span>
                      </td>
                      {/* Events */}
                      <td className="px-4 py-3 tabular-nums text-slate-300">
                        {agent.memory_counter.toLocaleString()}
                      </td>
                      {/* Last Active */}
                      <td className="px-4 py-3 text-slate-500" title={agent.created_at}>
                        {relativeTime(agent.created_at)}
                      </td>
                      {/* Trust Root */}
                      <td className="px-4 py-3">
                        <TruncatedId value={agent.trust_root} chars={10} />
                      </td>
                      {/* Actions */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Link href={`/agents/graph`}
                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px]
                                       text-slate-400 hover:border-violet-600/50 hover:text-violet-400 transition-colors">
                            Graph
                          </Link>
                          <Link href={`/memory/timeline?agent=${agent.id}`}
                            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-[11px]
                                       text-slate-400 hover:border-violet-600/50 hover:text-violet-400 transition-colors">
                            Memory
                          </Link>
                          {suiUrl && (
                            <a href={suiUrl} target="_blank" rel="noopener noreferrer"
                              className="flex items-center gap-0.5 rounded border border-slate-700 bg-slate-800
                                         px-2 py-1 text-[11px] text-slate-400 hover:text-blue-400 transition-colors">
                              Sui <ExternalLink className="h-2.5 w-2.5" />
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}
