"use client";

import { Explainer } from "@/components/explainer";
import { GitBranch } from "lucide-react";

export default function MemoryPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <GitBranch className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Memory Timeline</h1>
      </div>

      <Explainer title="Internal Mechanics: Materialized Projections">
        <p>
          WalrusOS doesn't store state—it projects it. The <strong>MemoryEngine</strong> listens to the immutable 
          stream of <code>ProtocolEvents</code> and builds a materialized view (like this timeline) in a local SQLite cache. 
          If the cache is destroyed, the exact same timeline is re-projected deterministically from the Walrus blob ledger.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="space-y-4 border-l-2 border-slate-800 ml-4 pl-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="relative">
            <span className="absolute -left-[25px] top-1 h-3 w-3 rounded-full bg-violet-500 ring-4 ring-slate-950" />
            <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
              <div className="text-sm font-mono text-slate-500 mb-2">Event {Math.random().toString(16).slice(2, 10)}</div>
              <div className="text-slate-300">Agent {i} performed an action...</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
