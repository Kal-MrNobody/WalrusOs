"use client";

import { Explainer } from "@/components/explainer";
import { FastForward, Play, Square, RotateCcw } from "lucide-react";

export default function ReplayPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <FastForward className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Replay Engine</h1>
      </div>

      <Explainer title="Internal Mechanics: Time Travel">
        <p>
          Because state is never mutated in WalrusOS, developers can "time travel". 
          The <strong>Replay Engine</strong> can reconstruct the exact state of an Agent, Workspace, or Stream 
          up to any specific <code>event_id</code> or timestamp. It does this by clearing the SQLite projection 
          and feeding the ProtocolEvents back through the EventStore one by one.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6">
        <div className="flex items-center justify-between mb-8">
          <div className="text-slate-400 font-mono text-sm">Target: stream_collaboration</div>
          <div className="text-emerald-400 font-mono text-sm">Epoch: 142</div>
        </div>
        
        <div className="h-2 w-full rounded-full bg-slate-800 mb-8">
          <div className="h-full rounded-full bg-violet-500 w-[65%]" />
        </div>

        <div className="flex justify-center gap-4">
          <button className="p-3 rounded-full bg-slate-800 text-slate-300 hover:text-white"><RotateCcw className="h-5 w-5" /></button>
          <button className="p-3 rounded-full bg-violet-600 text-white"><Play className="h-5 w-5 fill-current" /></button>
          <button className="p-3 rounded-full bg-slate-800 text-slate-300 hover:text-white"><Square className="h-5 w-5 fill-current" /></button>
        </div>
      </div>
    </div>
  );
}
