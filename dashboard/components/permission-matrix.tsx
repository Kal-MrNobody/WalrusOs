"use client";

import { useState } from "react";
import type { Permission } from "@/lib/api";

const VERB_STYLE: Record<string, string> = {
  READ:  "bg-sky-500/20 text-sky-300 border border-sky-500/30",
  WRITE: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
};

interface Props {
  permissions: Permission[];
  onRevoke: (id: string) => void;
}

export function PermissionMatrix({ permissions, onRevoke }: Props) {
  const [revoking, setRevoking] = useState<string | null>(null);

  const handleRevoke = async (id: string) => {
    setRevoking(id);
    await new Promise((r) => setTimeout(r, 500));
    onRevoke(id);
    setRevoking(null);
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-900/60">
            {["Agent", "Stream", "Verbs", "Granted", "Valid Until", ""].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {permissions.map((p) => (
            <tr key={p.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
              <td className="px-4 py-3 text-slate-200 font-medium">{p.agent}</td>
              <td className="px-4 py-3 text-violet-400 font-mono text-xs">{p.stream}</td>
              <td className="px-4 py-3">
                <div className="flex gap-1">
                  {p.verbs.map((v) => (
                    <span key={v} className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${VERB_STYLE[v] ?? "bg-slate-700 text-slate-300"}`}>{v}</span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-3 text-slate-500 text-xs">{p.granted_at}</td>
              <td className="px-4 py-3 text-slate-500 text-xs">{p.valid_until}</td>
              <td className="px-4 py-3">
                <button
                  onClick={() => handleRevoke(p.id)}
                  disabled={revoking === p.id}
                  className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-1 text-xs text-red-400 hover:bg-red-500/20 disabled:opacity-50 transition-colors"
                >
                  {revoking === p.id ? "Revoking…" : "Revoke"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
