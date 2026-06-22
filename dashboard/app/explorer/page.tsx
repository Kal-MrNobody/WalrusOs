"use client";

import { useEffect, useState } from "react";
import { Search, ExternalLink, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { BlobExplorer, SuiObjectExplorer } from "@/lib/api";
import { TruncatedId, CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// Known IDs from CLAUDE.md
const LEDGER_ANCHOR_ID = "0x0f96188ee403ecc58bd498fb874ef3037078775deb68e2061964ac1d3827e27d";
const PACKAGE_ID       = "0x3339a7cf05650525acb7233eb68c584974b164c4ff03d65e3de8169e41d369e8";

// ── Helpers ───────────────────────────────────────────────────────────────────

function FieldRow({ label, value, mono = true, link }: {
  label: string; value: string | number | boolean | null | undefined;
  mono?: boolean; link?: string;
}) {
  const display = value == null ? "—" : String(value);
  return (
    <div className="flex gap-3 py-1.5 text-sm border-b border-slate-800/60 last:border-0">
      <span className="w-32 shrink-0 text-slate-500">{label}</span>
      <span className={cn("min-w-0 flex-1 break-all text-slate-200", mono && "font-mono text-xs")}>
        {link ? (
          <a href={link} target="_blank" rel="noopener noreferrer"
             className="text-violet-400 hover:text-violet-300 inline-flex items-center gap-1">
            {display} <ExternalLink className="h-3 w-3" />
          </a>
        ) : display}
        {mono && typeof value === "string" && value.length > 0 && (
          <CopyButton text={value} className="ml-1" />
        )}
      </span>
    </div>
  );
}

function StatusBadge({ found }: { found: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
      found
        ? "bg-emerald-900/40 text-emerald-400 border border-emerald-800"
        : "bg-red-900/40 text-red-400 border border-red-800"
    )}>
      {found
        ? <><CheckCircle className="h-3.5 w-3.5" /> Found</>
        : <><XCircle className="h-3.5 w-3.5" /> Not Found</>}
    </span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-4 mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
      {children}
    </p>
  );
}

// ── Blob Explorer Panel ───────────────────────────────────────────────────────

function BlobPanel() {
  const [blobId, setBlobId]     = useState("");
  const [result, setResult]     = useState<BlobExplorer | null>(null);
  const [loading, setLoading]   = useState(false);

  const fetch_ = async (id = blobId) => {
    const target = id.trim();
    if (!target) return;
    setLoading(true);
    setResult(null);
    try {
      const data = await api.explorer.blob(target);
      setResult(data);
    } catch (e) {
      setResult({ found: false, blob_id: target, error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const content = result?.content;
  const contentStr = typeof content === "string"
    ? content
    : content != null
      ? JSON.stringify(content, null, 2)
      : null;

  // Helper: extract a field from decoded content
  const field = (key: string): string => {
    if (!content || typeof content === "string") return "";
    const obj = content as Record<string, unknown>;
    return obj[key] != null ? String(obj[key]) : "";
  };

  const agentName   = field("author") || field("agent_name");
  const agentId     = field("agent_id");
  const streamId    = field("stream_id");
  const ts          = field("timestamp") || field("created_at");
  const memoryType  = field("memory_type") || field("class_type");
  const rawTags     = typeof content === "object" && content
    ? (content as Record<string, unknown>)["tags"]
    : null;
  const tags = Array.isArray(rawTags) ? (rawTags as string[]).join(", ") : "";
  const sig  = field("signature") || field("sig");
  const pubKey = field("public_key");

  // Reconstruct developer content (strip internal fields)
  const INTERNAL = new Set([
    "author","agent_id","trust_root","public_key","workspace_id",
    "stream_id","class_type","memory_type","tags","importance","summary","project",
    "signature","timestamp","created_at",
  ]);
  const devContent = (content && typeof content === "object" && !Array.isArray(content))
    ? Object.fromEntries(
        Object.entries(content as Record<string, unknown>).filter(([k]) => !INTERNAL.has(k))
      )
    : null;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <div className="h-3 w-3 rounded-full bg-violet-500" />
        <h2 className="text-base font-semibold text-slate-100">Walrus Blob Explorer</h2>
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          suppressHydrationWarning
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm
                     font-mono text-slate-100 placeholder-slate-600 outline-none
                     focus:border-violet-500 focus:ring-1 focus:ring-violet-500/40"
          placeholder="Enter blob ID…"
          value={blobId}
          onChange={e => setBlobId(e.target.value)}
          onKeyDown={e => e.key === "Enter" && fetch_()}
        />
        <button
          onClick={() => fetch_()}
          disabled={loading || !blobId.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm
                     font-medium text-white transition-colors hover:bg-violet-500
                     disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Fetch
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="mt-4 min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-4 flex items-center justify-between">
            <StatusBadge found={result.found} />
            {result.found && result.walrus_url && (
              <a href={result.walrus_url} target="_blank" rel="noopener noreferrer"
                 className="flex items-center gap-1 text-xs text-slate-500 hover:text-violet-400">
                View raw on Walrus <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {!result.found ? (
            <p className="text-sm text-red-400">{result.error}</p>
          ) : (
            <div className="font-mono text-xs">
              <FieldRow label="Blob ID" value={result.blob_id} />
              <FieldRow label="Size" value={result.size != null ? `${result.size} bytes` : null} mono={false} />
              <FieldRow label="Compressed" value="yes" mono={false} />

              {(agentName || agentId || streamId || ts || memoryType) && (
                <>
                  <SectionTitle>Decoded Content</SectionTitle>
                  {agentName && <FieldRow label="Agent" value={`${agentName}${agentId ? ` (${agentId.slice(0, 16)}…)` : ""}`} />}
                  {streamId  && <FieldRow label="Stream" value={streamId} />}
                  {ts        && <FieldRow label="Timestamp" value={ts} />}
                  {memoryType && <FieldRow label="Memory Type" value={memoryType} mono={false} />}
                  {tags      && <FieldRow label="Tags" value={tags} mono={false} />}
                </>
              )}

              {devContent && Object.keys(devContent).length > 0 && (
                <>
                  <SectionTitle>Content</SectionTitle>
                  <pre className="whitespace-pre-wrap break-all rounded bg-slate-800/60 p-3 text-slate-300">
                    {JSON.stringify(devContent, null, 2)}
                  </pre>
                </>
              )}

              {(sig || pubKey) && (
                <>
                  <SectionTitle>Cryptographic Proof</SectionTitle>
                  {sig    && <FieldRow label="Signature" value={sig.slice(0, 32) + "…"} />}
                  {pubKey && <FieldRow label="Public Key" value={pubKey.slice(0, 32) + "…"} />}
                  <FieldRow
                    label="Verified"
                    value={sig ? "✔ Signed" : "✗ No signature"}
                    mono={false}
                  />
                </>
              )}

              {!agentName && !devContent && contentStr && (
                <>
                  <SectionTitle>Raw Content</SectionTitle>
                  <pre className="whitespace-pre-wrap break-all rounded bg-slate-800/60 p-3 text-slate-300">
                    {contentStr.slice(0, 4000)}
                  </pre>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {!result && !loading && (
        <div className="mt-6 rounded-lg border border-dashed border-slate-800 py-10 text-center text-sm text-slate-600">
          Enter a blob ID to inspect its content and cryptographic proof
        </div>
      )}
    </div>
  );
}

// ── Sui Object Explorer Panel ─────────────────────────────────────────────────

function SuiPanel() {
  const [objectId, setObjectId] = useState(LEDGER_ANCHOR_ID);
  const [result, setResult]     = useState<SuiObjectExplorer | null>(null);
  const [loading, setLoading]   = useState(false);

  const fetch_ = async (id = objectId) => {
    const target = id.trim();
    if (!target) return;
    setObjectId(target);
    setLoading(true);
    setResult(null);
    try {
      const data = await api.explorer.object(target);
      setResult(data);
    } catch (e) {
      setResult({ found: false, object_id: target, error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  // Auto-load LedgerAnchor on mount
  useEffect(() => { fetch_(LEDGER_ANCHOR_ID); }, []); // eslint-disable-line

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <div className="h-3 w-3 rounded-full bg-blue-500" />
        <h2 className="text-base font-semibold text-slate-100">Sui Object Explorer</h2>
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          suppressHydrationWarning
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm
                     font-mono text-slate-100 placeholder-slate-600 outline-none
                     focus:border-blue-500 focus:ring-1 focus:ring-blue-500/40"
          placeholder="Enter object ID or tx digest…"
          value={objectId}
          onChange={e => setObjectId(e.target.value)}
          onKeyDown={e => e.key === "Enter" && fetch_()}
        />
        <button
          onClick={() => fetch_()}
          disabled={loading || !objectId.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm
                     font-medium text-white transition-colors hover:bg-blue-500
                     disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          Fetch
        </button>
      </div>

      {/* Quick-access buttons */}
      <div className="mt-2 flex gap-2">
        <button
          onClick={() => fetch_(LEDGER_ANCHOR_ID)}
          className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs
                     text-slate-400 hover:border-blue-600/50 hover:text-blue-400 transition-colors"
        >
          LedgerAnchor
        </button>
        <button
          onClick={() => fetch_(PACKAGE_ID)}
          className="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs
                     text-slate-400 hover:border-blue-600/50 hover:text-blue-400 transition-colors"
        >
          Package
        </button>
      </div>

      {/* Results */}
      {loading && (
        <div className="mt-6 flex items-center justify-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Querying Sui testnet…
        </div>
      )}

      {result && !loading && (
        <div className="mt-4 min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-4 flex items-center justify-between">
            <StatusBadge found={result.found} />
            {result.found && result.sui_explorer_url && (
              <a href={result.sui_explorer_url} target="_blank" rel="noopener noreferrer"
                 className="flex items-center gap-1 text-xs text-slate-500 hover:text-blue-400">
                View on Sui Explorer <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>

          {!result.found ? (
            <p className="text-sm text-red-400">{result.error}</p>
          ) : (
            <div className="font-mono text-xs">
              <FieldRow label="Object ID"  value={result.object_id} />
              <FieldRow label="Type"       value={result.object_type} />
              <FieldRow label="Owner"      value={result.owner} />
              <FieldRow label="Version"    value={result.version} mono={false} />
              <FieldRow label="Digest"     value={result.digest} />

              {result.fields && Object.keys(result.fields).length > 0 && (
                <>
                  <SectionTitle>Fields</SectionTitle>
                  {Object.entries(result.fields).map(([k, v]) => (
                    <FieldRow
                      key={k}
                      label={k}
                      value={typeof v === "object" ? JSON.stringify(v) : String(v)}
                    />
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExplorerPage() {
  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Search className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Protocol Explorer</h1>
          <p className="text-sm text-slate-500">Inspect Walrus blobs and Sui objects directly</p>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="flex gap-5" style={{ minHeight: "calc(100vh - 180px)" }}>
        <div className="flex-1 min-w-0">
          <BlobPanel />
        </div>
        <div className="w-px bg-slate-800 shrink-0" />
        <div className="flex-1 min-w-0">
          <SuiPanel />
        </div>
      </div>
    </div>
  );
}
