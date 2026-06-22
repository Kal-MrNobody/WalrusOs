"use client";

import { useEffect, useState } from "react";
import { Shield, AlertCircle, Trash2, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import type { Permission } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

const VERB_STYLE: Record<string, string> = {
  read:    "bg-blue-900/40 text-blue-400 border-blue-800",
  write:   "bg-violet-900/40 text-violet-400 border-violet-800",
  publish: "bg-emerald-900/40 text-emerald-400 border-emerald-800",
  admin:   "bg-red-900/40 text-red-400 border-red-800",
};

function VerbBadge({ verb }: { verb: string }) {
  return (
    <span className={cn(
      "inline-flex rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
      VERB_STYLE[verb.toLowerCase()] ?? "bg-slate-800 text-slate-400 border-slate-700"
    )}>
      {verb}
    </span>
  );
}

function relativeTime(ts: string) {
  if (!ts) return "—";
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

export default function PermissionsPage() {
  const [perms, setPerms]   = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  useEffect(() => {
    api.permissions.list()
      .then(setPerms)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function revoke(id: string) {
    setRevoking(id);
    try {
      await api.permissions.revoke(id);
      setPerms(p => p.filter(x => x.id !== id));
    } catch (e) {
      setError(String(e));
    } finally {
      setRevoking(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Shield className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">Permissions</h1>
          <p className="text-sm text-slate-500">Capability grants between agents and streams</p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </div>
      )}

      {/* Verb legend */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
        <span className="text-xs text-slate-500 font-medium mr-2">Verbs:</span>
        {["read", "write", "publish", "admin"].map(v => (
          <VerbBadge key={v} verb={v} />
        ))}
      </div>

      <div className="rounded-xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60">
              {["Agent", "Stream", "Verbs", "Granted", "Valid Until", ""].map(h => (
                <th key={h} className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? [...Array(4)].map((_, i) => (
                <tr key={i} className="border-b border-slate-800/60">
                  {[...Array(6)].map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <div className="h-4 w-20 animate-pulse rounded bg-slate-800" />
                    </td>
                  ))}
                </tr>
              ))
              : perms.length === 0
                ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-slate-600">
                      No capability grants found. Use <code className="bg-slate-800 rounded px-1">agent.delegate()</code> to grant access.
                    </td>
                  </tr>
                )
                : perms.map(p => (
                  <tr key={p.id} className="border-b border-slate-800/40 hover:bg-slate-800/30 transition-colors">
                    <td className="px-4 py-3">
                      {p.agent_name && p.agent_name !== "—"
                        ? <span className="text-slate-200 text-sm font-medium">{p.agent_name}</span>
                        : <TruncatedId value={p.agent} chars={12} />}
                    </td>
                    <td className="px-4 py-3">
                      {p.stream_name && p.stream_name !== p.stream
                        ? <span className="text-slate-300 text-sm">{p.stream_name}</span>
                        : <TruncatedId value={p.stream} chars={12} />}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(p.verbs ?? []).map(v => <VerbBadge key={v} verb={v} />)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs" title={p.granted_at}>
                      {relativeTime(p.granted_at)}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs"
                        title={p.valid_until_label || p.valid_until}>
                      {p.valid_until_label
                        ? p.valid_until_label
                        : (p.valid_until
                            ? new Date(p.valid_until).toLocaleDateString()
                            : "—")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {p.sui_object_url && (
                          <a
                            href={p.sui_object_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="View capability object on Sui Explorer"
                            className="flex items-center gap-1 rounded border border-violet-900 bg-violet-950/30
                                       px-2 py-1 text-[11px] text-violet-300 hover:bg-violet-900/40 transition-colors"
                          >
                            <ExternalLink className="h-3 w-3" />
                            Sui
                          </a>
                        )}
                        <button
                          onClick={() => revoke(p.id)}
                          disabled={revoking === p.id}
                          className="flex items-center gap-1 rounded border border-red-900 bg-red-950/40
                                     px-2 py-1 text-[11px] text-red-500 hover:bg-red-900/40 transition-colors
                                     disabled:opacity-50"
                        >
                          <Trash2 className="h-3 w-3" />
                          {revoking === p.id ? "…" : "Revoke"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>
    </div>
  );
}
