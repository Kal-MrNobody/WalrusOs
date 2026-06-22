"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { Search, Clock, Zap, Tag, GitBranch } from "lucide-react";
import { api } from "@/lib/api";
import type { MemorySearchResult } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

const TYPE_COLOR: Record<string, string> = {
  observation: "text-blue-400 bg-blue-900/30 border-blue-800",
  decision:    "text-violet-400 bg-violet-900/30 border-violet-800",
  artifact:    "text-emerald-400 bg-emerald-900/30 border-emerald-800",
  summary:     "text-amber-400 bg-amber-900/30 border-amber-800",
  error:       "text-red-400 bg-red-900/30 border-red-800",
};

function relativeTime(ts: string) {
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(100, Math.round(score * 100));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-slate-800 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all",
            pct > 80 ? "bg-violet-500" : pct > 50 ? "bg-blue-500" : "bg-slate-600")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] tabular-nums text-slate-500">{pct}%</span>
    </div>
  );
}

function ResultCard({ result }: { result: MemorySearchResult }) {
  const typeClass = TYPE_COLOR[result.memory_type] ?? "text-slate-400 bg-slate-800 border-slate-700";
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200 leading-relaxed line-clamp-3">{result.text}</p>
        </div>
        <ScoreBar score={result.score} />
      </div>

      <div className="mt-3 pt-3 border-t border-slate-800 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-slate-500">
        <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium", typeClass)}>
          {result.memory_type}
        </span>
        <span className="flex items-center gap-1">
          <span className="text-slate-600">Agent:</span> {result.agent_name}
        </span>
        <Link
          href={`/memory/timeline?stream=${result.stream_id}`}
          className="flex items-center gap-1 hover:text-violet-400 transition-colors"
        >
          <GitBranch className="h-3 w-3" />
          <TruncatedId value={result.stream_id} chars={10} />
        </Link>
        <span className="flex items-center gap-1 ml-auto">
          <Clock className="h-3 w-3" /> {relativeTime(result.timestamp)}
        </span>
      </div>
    </div>
  );
}

export default function SearchPage() {
  const [query, setQuery]         = useState("");
  const [results, setResults]     = useState<MemorySearchResult[]>([]);
  const [loading, setLoading]     = useState(false);
  const [searched, setSearched]   = useState(false);
  const [searchTime, setSearchTime] = useState<number | null>(null);
  const [error, setError]         = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    const t0 = performance.now();
    try {
      const res = await api.search.memory(q.trim(), 30);
      setResults(res);
      setSearchTime(performance.now() - t0);
      setSearched(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") doSearch(query);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Search className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Memory Search</h1>
          <p className="text-sm text-slate-500">Semantic search across all agent memory events</p>
        </div>
      </div>

      {/* Search input */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search memory events… (press Enter)"
            className="w-full rounded-xl border border-slate-700 bg-slate-900 py-3 pl-10 pr-4 text-sm
                       text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-violet-600
                       focus:ring-1 focus:ring-violet-600/30 transition-all"
          />
        </div>
        <button
          onClick={() => doSearch(query)}
          disabled={loading || !query.trim()}
          className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-medium
                     text-white hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Zap className="h-4 w-4" />
          {loading ? "Searching…" : "Search"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Results meta */}
      {searched && !loading && (
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>{results.length} result{results.length !== 1 ? "s" : ""}</span>
          {searchTime != null && (
            <>
              <span className="text-slate-700">·</span>
              <span>{searchTime.toFixed(0)} ms</span>
            </>
          )}
          {results.length > 0 && (
            <>
              <span className="text-slate-700">·</span>
              <span>sorted by relevance</span>
            </>
          )}
        </div>
      )}

      {/* Loading skeletons */}
      {loading && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
          ))}
        </div>
      )}

      {/* Results */}
      {!loading && results.length > 0 && (
        <div className="space-y-3">
          {results.map(r => <ResultCard key={r.id} result={r} />)}
        </div>
      )}

      {/* Empty state */}
      {!loading && searched && results.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <Search className="h-10 w-10 text-slate-700" />
          <p className="text-sm text-slate-500">No results for <span className="text-slate-300">"{query}"</span></p>
          <p className="text-xs text-slate-700">Try a broader query or check that memory events exist</p>
        </div>
      )}

      {/* Idle hint */}
      {!searched && !loading && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-700">
          <Search className="h-12 w-12" />
          <p className="text-sm">Type a query above to search agent memories</p>
        </div>
      )}
    </div>
  );
}
