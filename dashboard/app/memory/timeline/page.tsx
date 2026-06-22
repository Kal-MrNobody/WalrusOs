"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { GitBranch, ExternalLink, ChevronDown, X, CheckCircle, XCircle, Copy } from "lucide-react";
import { api } from "@/lib/api";
import type { MemoryEventItem, Stream, Agent } from "@/lib/api";
import { TruncatedId, CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// ── Constants ─────────────────────────────────────────────────────────────────

const MEMORY_TYPES = [
  "observation", "decision", "bug", "insight", "summary", "artifact",
  "episodic", "semantic", "procedural", "working",
];

const TYPE_COLOR: Record<string, string> = {
  observation:  "bg-violet-600",
  decision:     "bg-blue-500",
  bug:          "bg-red-500",
  insight:      "bg-emerald-500",
  summary:      "bg-amber-500",
  artifact:     "bg-slate-500",
  episodic:     "bg-violet-500",
  semantic:     "bg-cyan-500",
  procedural:   "bg-orange-500",
  working:      "bg-teal-500",
};

const TYPE_BADGE: Record<string, string> = {
  observation:  "bg-violet-900/50 text-violet-300 border-violet-800",
  decision:     "bg-blue-900/50 text-blue-300 border-blue-800",
  bug:          "bg-red-900/50 text-red-300 border-red-800",
  insight:      "bg-emerald-900/50 text-emerald-300 border-emerald-800",
  summary:      "bg-amber-900/50 text-amber-300 border-amber-800",
  artifact:     "bg-slate-800 text-slate-300 border-slate-700",
  episodic:     "bg-violet-900/50 text-violet-300 border-violet-800",
  semantic:     "bg-cyan-900/50 text-cyan-300 border-cyan-800",
  procedural:   "bg-orange-900/50 text-orange-300 border-orange-800",
  working:      "bg-teal-900/50 text-teal-300 border-teal-800",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(ts: string): string {
  if (!ts) return "";
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function dateLabel(ts: string): string {
  if (!ts) return "Unknown";
  const d = new Date(ts);
  const now = new Date();
  const dayDiff = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (dayDiff === 0) return "Today";
  if (dayDiff === 1) return "Yesterday";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function dateKey(ts: string): string {
  if (!ts) return "unknown";
  return new Date(ts).toISOString().slice(0, 10);
}

function typeBadgeClass(type: string): string {
  const key = type.toLowerCase().replace("memorytype.", "");
  return TYPE_BADGE[key] ?? "bg-slate-800 text-slate-400 border-slate-700";
}

function typeBarColor(type: string): string {
  const key = type.toLowerCase().replace("memorytype.", "");
  return TYPE_COLOR[key] ?? "bg-slate-600";
}

function normalizeType(type: string): string {
  return type.toLowerCase().replace("memorytype.", "").replace("_", " ");
}

function statusDot(status: string) {
  const c = status === "active" ? "bg-emerald-500"
    : status === "paused" ? "bg-amber-500"
    : "bg-red-500";
  return <span className={cn("inline-block h-1.5 w-1.5 rounded-full", c)} />;
}

// ── Importance Bar ────────────────────────────────────────────────────────────

function ImportanceBar({ value }: { value: number }) {
  const pct = Math.round((value ?? 0) * 100);
  const color = pct >= 80 ? "bg-violet-500" : pct >= 50 ? "bg-blue-500" : "bg-slate-600";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-slate-800 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-600">{pct}%</span>
    </div>
  );
}

// ── Filter Dropdown ───────────────────────────────────────────────────────────

function FilterSelect({
  label, value, onChange, options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="appearance-none rounded-lg border border-slate-700 bg-slate-800 pl-3 pr-8 py-2
                   text-sm text-slate-300 outline-none focus:border-violet-500 cursor-pointer"
      >
        <option value="">{label}</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-2.5 h-3.5 w-3.5 text-slate-500" />
    </div>
  );
}

// ── Event Card ────────────────────────────────────────────────────────────────

function EventCard({
  event,
  onClick,
  selected,
  search,
}: {
  event: MemoryEventItem;
  onClick: () => void;
  selected: boolean;
  search: string;
}) {
  const mtype   = normalizeType(event.memory_type);
  const barColor = typeBarColor(event.memory_type);
  const walrusUrl = event.blob_id
    ? `https://aggregator.walrus-testnet.walrus.space/v1/blobs/${event.blob_id}`
    : null;

  // Build display content from event.content
  const contentEntries = Object.entries(event.content ?? {}).filter(
    ([, v]) => v != null && String(v).trim() !== ""
  );

  // Highlight search match
  const contentStr = contentEntries.map(([k, v]) => `${k}: ${String(v)}`).join(" ");
  const matchesSearch = !search || contentStr.toLowerCase().includes(search.toLowerCase())
    || event.agent_name.toLowerCase().includes(search.toLowerCase())
    || mtype.includes(search.toLowerCase());

  if (!matchesSearch) return null;

  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative flex cursor-pointer gap-0 rounded-lg border transition-all",
        selected
          ? "border-violet-600/60 bg-violet-950/30"
          : "border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-800/30"
      )}
    >
      {/* Left color bar */}
      <div className={cn("w-1 rounded-l-lg shrink-0", barColor)} />

      <div className="flex-1 min-w-0 p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold text-sm text-slate-200 truncate">
              {event.agent_name || "Unknown"}
            </span>
            <span className={cn(
              "shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium",
              typeBadgeClass(event.memory_type)
            )}>
              {mtype}
            </span>
            {(event.tags ?? []).map(tag => (
              <span key={tag}
                className="shrink-0 rounded-full bg-violet-900/30 border border-violet-800/40
                           px-2 py-0.5 text-[10px] text-violet-400">
                {tag}
              </span>
            ))}
          </div>
          <span
            className="shrink-0 text-xs text-slate-500"
            title={event.timestamp}
          >
            {relativeTime(event.timestamp)}
          </span>
        </div>

        {/* Content */}
        {contentEntries.length > 0 ? (
          <div className="text-sm text-slate-300 space-y-0.5">
            {contentEntries.slice(0, 4).map(([k, v]) => (
              <p key={k} className="truncate">
                <span className="text-slate-600 mr-1">{k}:</span>
                <span>{String(v)}</span>
              </p>
            ))}
            {contentEntries.length > 4 && (
              <p className="text-slate-600 text-xs">+{contentEntries.length - 4} more fields</p>
            )}
          </div>
        ) : event.summary ? (
          <p className="text-sm text-slate-300">{event.summary}</p>
        ) : (
          <p className="text-sm text-slate-600 italic">No content</p>
        )}

        {/* Footer row */}
        <div className="mt-3 flex items-center gap-4 text-[11px]">
          <ImportanceBar value={event.importance} />
          {event.blob_id && (
            <div className="flex items-center gap-1 text-slate-600">
              <span className="font-mono">{event.blob_id.slice(0, 16)}…</span>
              <CopyButton text={event.blob_id} />
              {walrusUrl && (
                <a href={walrusUrl} target="_blank" rel="noopener noreferrer"
                   className="hover:text-violet-400" onClick={e => e.stopPropagation()}>
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          )}
          <span className={cn(
            "flex items-center gap-1",
            event.verified ? "text-emerald-500" : "text-slate-600"
          )}>
            {event.verified
              ? <><CheckCircle className="h-3 w-3" /> Verified</>
              : <><XCircle className="h-3 w-3" /> Unverified</>}
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Detail Panel ──────────────────────────────────────────────────────────────

function DetailPanel({
  event,
  onClose,
}: {
  event: MemoryEventItem;
  onClose: () => void;
}) {
  const walrusUrl = event.blob_id
    ? `https://aggregator.walrus-testnet.walrus.space/v1/blobs/${event.blob_id}`
    : null;
  const suiUrl = event.tx_digest
    ? `https://suiexplorer.com/txblock/${event.tx_digest}?network=testnet`
    : null;

  function Row({ label, value, link }: { label: string; value: string; link?: string }) {
    if (!value) return null;
    return (
      <div className="border-b border-slate-800/60 py-2 last:border-0">
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-0.5">{label}</p>
        <div className="flex items-start gap-1.5">
          {link ? (
            <a href={link} target="_blank" rel="noopener noreferrer"
               className="break-all font-mono text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1">
              {value} <ExternalLink className="h-3 w-3 shrink-0" />
            </a>
          ) : (
            <span className="break-all font-mono text-xs text-slate-300">{value}</span>
          )}
          <CopyButton text={value} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Event Detail</h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="overflow-y-auto">
        <Row label="Event ID"  value={event.id} />
        <Row label="Blob ID"   value={event.blob_id}  link={walrusUrl ?? undefined} />
        <Row label="Tx Digest" value={event.tx_digest} link={suiUrl ?? undefined} />
        <Row label="Agent ID"  value={event.agent_id} />
        <Row label="Stream ID" value={event.stream_id} />
        <Row label="Event Hash" value={event.event_hash} />
        {event.signature && (
          <div className="border-b border-slate-800/60 py-2">
            <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-0.5">Signature</p>
            <p className="break-all font-mono text-xs text-slate-400">
              {event.signature.slice(0, 64)}
              {event.signature.length > 64 && (
                <span className="text-slate-600">…{event.signature.length} chars</span>
              )}
            </p>
          </div>
        )}
        {event.public_key && (
          <div className="border-b border-slate-800/60 py-2">
            <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-0.5">Public Key</p>
            <p className="break-all font-mono text-xs text-slate-400">{event.public_key.slice(0, 48)}…</p>
          </div>
        )}
        <div className="py-2">
          <p className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">Verification</p>
          <div className="space-y-1 text-xs">
            <div className={cn("flex items-center gap-1.5", event.verified ? "text-emerald-400" : "text-slate-600")}>
              {event.verified ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              Signature {event.verified ? "valid" : "missing"}
            </div>
            <div className={cn("flex items-center gap-1.5", event.blob_id ? "text-emerald-400" : "text-slate-600")}>
              {event.blob_id ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              Blob {event.blob_id ? "anchored" : "missing"}
            </div>
            <div className={cn("flex items-center gap-1.5", event.tx_digest ? "text-emerald-400" : "text-slate-600")}>
              {event.tx_digest ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
              Sui tx {event.tx_digest ? "anchored" : "not anchored"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const LIMITS = [
  { value: "50",  label: "Latest 50" },
  { value: "200", label: "Latest 200" },
  { value: "500", label: "Latest 500" },
];

export default function MemoryTimelinePage() {
  const [events, setEvents]     = useState<MemoryEventItem[]>([]);
  const [streams, setStreams]   = useState<Stream[]>([]);
  const [agents, setAgents]     = useState<Agent[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [selected, setSelected] = useState<MemoryEventItem | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Filters
  const [search, setSearch]         = useState("");
  const [filterStream, setFStream]  = useState("");
  const [filterAgent, setFAgent]    = useState("");
  const [filterType, setFType]      = useState("");
  const [limit, setLimit]           = useState("50");

  const load = (params?: { stream?: string; agent?: string; type?: string; lim?: string }) => {
    setLoading(true);
    api.memory.events({
      stream:      (params?.stream ?? filterStream) || undefined,
      agent:       (params?.agent  ?? filterAgent)  || undefined,
      memory_type: (params?.type   ?? filterType)   || undefined,
      limit:       Number(params?.lim ?? limit),
    })
      .then(setEvents)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  };

  // Load metadata (streams + agents) for filter dropdowns
  useEffect(() => {
    Promise.all([api.streams.list(), api.agents.listAll()])
      .then(([s, a]) => { setStreams(s); setAgents(a); })
      .catch(() => {});
    load();
  }, []); // eslint-disable-line

  // Re-load when filters change
  useEffect(() => { load(); }, [filterStream, filterAgent, filterType, limit]); // eslint-disable-line

  // Escape key closes panel; click-outside closes panel
  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setSelected(null); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected]);

  // Group events by date for section headers
  const grouped = useMemo(() => {
    const filtered = events.filter(ev => {
      if (!search) return true;
      const hay = [
        ev.agent_name,
        normalizeType(ev.memory_type),
        ...ev.tags,
        ...Object.values(ev.content ?? {}).map(String),
      ].join(" ").toLowerCase();
      return hay.includes(search.toLowerCase());
    });

    const map = new Map<string, MemoryEventItem[]>();
    for (const ev of filtered) {
      const key = dateKey(ev.timestamp);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(ev);
    }
    return Array.from(map.entries()).map(([key, items]) => ({
      key,
      label: dateLabel(items[0].timestamp),
      items,
    }));
  }, [events, search]);

  const streamOptions = streams.map(s => ({ value: s.id, label: s.name ?? s.id.slice(0, 14) }));
  const agentOptions  = agents.map(a => ({ value: a.id, label: a.name }));
  const typeOptions   = MEMORY_TYPES.map(t => ({ value: t, label: t }));

  return (
    <div className="flex flex-col gap-4" style={{ height: "calc(100vh - 80px)" }}>
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4 shrink-0">
        <GitBranch className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Memory Timeline</h1>
          <p className="text-sm text-slate-500">
            {events.length} event{events.length !== 1 ? "s" : ""} · cryptographically signed memory
          </p>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 shrink-0">
        <input
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm
                     text-slate-300 placeholder-slate-600 outline-none focus:border-violet-500
                     min-w-[200px] flex-1"
          placeholder="Filter by content, agent, or type…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <FilterSelect
          label="All Streams"
          value={filterStream}
          onChange={setFStream}
          options={streamOptions}
        />
        <FilterSelect
          label="All Agents"
          value={filterAgent}
          onChange={setFAgent}
          options={agentOptions}
        />
        <FilterSelect
          label="All Types"
          value={filterType}
          onChange={setFType}
          options={typeOptions}
        />
        <div className="flex rounded-lg border border-slate-700 overflow-hidden">
          {LIMITS.map(l => (
            <button
              key={l.value}
              onClick={() => setLimit(l.value)}
              className={cn(
                "px-3 py-2 text-xs transition-colors",
                limit === l.value
                  ? "bg-violet-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              )}
            >
              {l.label}
            </button>
          ))}
        </div>
        {(filterStream || filterAgent || filterType || search) && (
          <button
            onClick={() => { setSearch(""); setFStream(""); setFAgent(""); setFType(""); }}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"
          >
            <X className="h-3.5 w-3.5" /> Clear
          </button>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400 shrink-0">
          {error} —{" "}
          <button onClick={() => load()} className="underline">Retry</button>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 min-h-0 gap-4">

        {/* Timeline */}
        <div className="flex-1 min-w-0 overflow-y-auto pr-1">
          {loading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-28 rounded-lg animate-pulse bg-slate-800/60" />
              ))}
            </div>
          ) : grouped.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-600">
              <GitBranch className="mb-3 h-10 w-10 opacity-25" />
              <p className="text-sm">No memory events yet</p>
              <p className="mt-1 text-xs">
                Run <code className="font-mono">python scripts/demo_recovery.py</code> to populate
              </p>
            </div>
          ) : (
            <div className="space-y-6 pb-8">
              {grouped.map(group => (
                <div key={group.key}>
                  {/* Date separator */}
                  <div className="mb-3 flex items-center gap-3">
                    <div className="h-px flex-1 bg-slate-800" />
                    <span className="text-xs font-medium text-slate-500">{group.label}</span>
                    <div className="h-px flex-1 bg-slate-800" />
                  </div>

                  <div className="space-y-2">
                    {group.items.map(ev => (
                      <EventCard
                        key={ev.id}
                        event={ev}
                        onClick={() => setSelected(sel => sel?.id === ev.id ? null : ev)}
                        selected={selected?.id === ev.id}
                        search={search}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Detail panel — slide-in */}
        {selected && (
          <>
            {/* click-outside overlay */}
            <div
              className="fixed inset-0 z-10"
              onClick={() => setSelected(null)}
            />
            <div
              ref={panelRef}
              className="relative z-20 w-80 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/60 p-4
                         animate-in slide-in-from-right-4 duration-200"
            >
              <DetailPanel event={selected} onClose={() => setSelected(null)} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
