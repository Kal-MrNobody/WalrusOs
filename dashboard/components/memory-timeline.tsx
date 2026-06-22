"use client";

import { useState } from "react";
import type { MemoryEventItem } from "@/lib/api";
import { ShieldCheck, ShieldAlert } from "lucide-react";

const TYPE_COLOR: Record<string, string> = {
  working:  "border-violet-500 bg-violet-500/10 text-violet-300",
  episodic: "border-emerald-500 bg-emerald-500/10 text-emerald-300",
  semantic: "border-amber-500 bg-amber-500/10 text-amber-300",
};

interface Props { events: MemoryEventItem[] }

export function MemoryTimeline({ events }: Props) {
  const [replaying, setReplaying] = useState(false);
  const [replayIdx, setReplayIdx] = useState<number | null>(null);

  const startReplay = async () => {
    setReplaying(true);
    for (let i = 0; i < events.length; i++) {
      setReplayIdx(i);
      await new Promise((r) => setTimeout(r, 600));
    }
    setReplaying(false);
    setReplayIdx(null);
  };

  return (
    <div className="flex flex-col gap-4">
      <button
        onClick={startReplay}
        disabled={replaying}
        className="self-start rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium
                   text-white hover:bg-violet-500 disabled:opacity-50 transition-colors"
      >
        {replaying ? "Replaying…" : "▶ Replay DAG"}
      </button>

      <div className="relative pl-6">
        <div className="absolute left-2 top-0 h-full w-0.5 bg-slate-800" />

        {events.map((ev, i) => {
          const isActive  = replayIdx !== null && i <= replayIdx;
          const isCurrent = replayIdx === i;
          const mtype = ev.memory_type ?? "observation";
          return (
            <div key={ev.id}
              className={`relative mb-4 transition-all duration-500 ${isActive ? "opacity-100" : replaying ? "opacity-30" : "opacity-100"}`}
            >
              <div className={`absolute -left-4 top-3 h-3 w-3 rounded-full border-2 transition-colors ${isCurrent ? "border-violet-400 bg-violet-400" : "border-slate-600 bg-slate-900"}`} />
              <div className={`ml-2 rounded-xl border p-4 transition-all duration-300 ${TYPE_COLOR[mtype] ?? "border-slate-700 bg-slate-800"} ${isCurrent ? "scale-[1.02]" : ""}`}>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xs font-mono text-slate-500">#{i}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold border ${TYPE_COLOR[mtype] ?? "border-slate-700"}`}>{mtype}</span>
                  <span className="text-slate-400 font-medium text-sm">{ev.agent_name}</span>
                  {ev.verified && (
                    <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded-sm border border-emerald-500/20">
                      <ShieldCheck className="w-3 h-3" /> Verified
                    </span>
                  )}
                  <span className="ml-auto text-xs text-slate-600">
                    {ev.timestamp ? new Date(ev.timestamp).toLocaleString() : ""}
                  </span>
                </div>
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap">
                  {JSON.stringify(ev.content, null, 2)}
                </pre>
                <div className="mt-2 text-[10px] text-slate-600 font-mono flex items-center gap-4">
                  <span>blob: {ev.blob_id}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
