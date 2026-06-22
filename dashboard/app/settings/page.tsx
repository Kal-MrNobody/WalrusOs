"use client";

import { useEffect, useState } from "react";
import { Settings2, ExternalLink, RefreshCw, Wifi, Database, Package } from "lucide-react";
import { api } from "@/lib/api";
import type { AppSettings } from "@/lib/api";
import { CopyButton, TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// ── Config code block with copy ───────────────────────────────────────────────

function CodeBlock({ label, code }: { label: string; code: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/60 px-4 py-2.5">
        <span className="text-xs font-medium text-slate-400">{label}</span>
        <CopyButton text={code} />
      </div>
      <pre className="overflow-x-auto p-4 text-[12px] font-mono text-slate-300 leading-relaxed">
        {code}
      </pre>
    </div>
  );
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-slate-800/60 last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <div className="text-sm text-slate-200">{children}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [syncing, setSyncing]   = useState(false);
  const [syncMsg, setSyncMsg]   = useState<string | null>(null);

  useEffect(() => {
    api.settings.get()
      .then(setSettings)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function sync() {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await api.workspaces.sync();
      setSyncMsg(r.status === "ok" ? "Synced successfully" : r.error ?? "Sync failed");
    } catch (e) {
      setSyncMsg(String(e));
    } finally {
      setSyncing(false);
    }
  }

  if (loading) return (
    <div className="space-y-4">
      <div className="h-8 w-48 animate-pulse rounded-lg bg-slate-800" />
      <div className="h-48 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
      <div className="h-48 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
    </div>
  );

  if (error) return (
    <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">{error}</div>
  );

  const s = settings!;

  return (
    <div className="space-y-8 max-w-3xl">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Settings2 className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Settings</h1>
          <p className="text-sm text-slate-500">Infrastructure configuration and integrations</p>
        </div>
      </div>

      {/* ── Infrastructure ── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Package className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Infrastructure</h2>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-5 divide-y divide-slate-800/60">
          <InfoRow label="Network">
            <span className="flex items-center gap-1.5">
              <Wifi className="h-3.5 w-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-medium">{s.network}</span>
            </span>
          </InfoRow>
          <InfoRow label="Package ID">
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-slate-400">{s.package_id.slice(0, 22)}…</span>
              <CopyButton text={s.package_id} />
              <a href={s.sui_explorer_package} target="_blank" rel="noopener noreferrer"
                className="text-blue-500 hover:text-blue-400">
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </InfoRow>
          <InfoRow label="LedgerAnchor">
            <div className="flex items-center gap-2 font-mono text-xs">
              <span className="text-slate-400">{s.ledger_anchor_id.slice(0, 22)}…</span>
              <CopyButton text={s.ledger_anchor_id} />
              <a href={s.sui_explorer_ledger} target="_blank" rel="noopener noreferrer"
                className="text-blue-500 hover:text-blue-400">
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </InfoRow>
          <InfoRow label="Wallet">
            <TruncatedId value={s.wallet} chars={20} />
          </InfoRow>
          <InfoRow label="Publisher URL">
            <span className="font-mono text-xs text-slate-400">{s.publisher_url}</span>
          </InfoRow>
          <InfoRow label="Aggregator URL">
            <span className="font-mono text-xs text-slate-400">{s.aggregator_url}</span>
          </InfoRow>
          <InfoRow label="SQLite Cache">
            <span className="font-mono text-xs text-slate-400 truncate max-w-56 block">{s.db_path}</span>
          </InfoRow>
        </div>

        {/* Sync button */}
        <div className="flex items-center gap-3">
          <button onClick={sync} disabled={syncing}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2
                       text-sm text-slate-300 hover:border-violet-600/50 hover:text-violet-300 transition-colors
                       disabled:opacity-50">
            <RefreshCw className={cn("h-3.5 w-3.5", syncing && "animate-spin")} />
            {syncing ? "Syncing…" : "Sync Workspace"}
          </button>
          {syncMsg && (
            <span className={cn("text-sm", syncMsg.includes("fail") || syncMsg.includes("Error")
              ? "text-red-400" : "text-emerald-400")}>
              {syncMsg}
            </span>
          )}
        </div>
      </section>

      {/* ── MCP Server ── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">MCP Server</h2>
        </div>

        <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
          <span className="text-sm text-slate-400">Status</span>
          <span className="ml-auto flex items-center gap-1.5 text-sm">
            <span className={cn("h-2 w-2 rounded-full",
              s.mcp_status === "running" ? "bg-emerald-500 animate-pulse" : "bg-slate-600")} />
            <span className={s.mcp_status === "running" ? "text-emerald-400" : "text-slate-500"}>
              {s.mcp_status}
            </span>
          </span>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
          <p className="text-xs text-slate-500 mb-2">Start the MCP server:</p>
          <code className="text-sm font-mono text-violet-300">walrusos mcp start</code>
        </div>

        <CodeBlock label="Claude Desktop — claude_desktop_config.json" code={s.claude_desktop_config} />
        <CodeBlock label="Cursor / Windsurf — .cursor/mcp.json" code={s.cursor_config} />
      </section>
    </div>
  );
}
