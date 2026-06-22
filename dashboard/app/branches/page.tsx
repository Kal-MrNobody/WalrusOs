"use client";

import { Explainer } from "@/components/explainer";
import { Split } from "lucide-react";

export default function BranchesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Split className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Branches</h1>
      </div>

      <Explainer title="Internal Mechanics: Zero-Cost Forks">
        <p>
          Just like Git, WalrusOS allows agents to branch timelines to explore alternative thoughts. 
          When <code>stream.fork()</code> is called, the protocol simply generates a new Stream UUID and appends a 
          special system event pointing to the source <code>event_id</code>. This means branching is instantaneous 
          and zero-cost. The new stream shares all cryptographic history with its parent up until the fork point.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-6 flex flex-col items-center">
        <div className="w-2 h-16 bg-violet-600 rounded-full" />
        <div className="w-32 h-2 bg-violet-600 rounded-full my-1" />
        <div className="flex gap-24">
          <div className="w-2 h-16 bg-violet-600 rounded-full" />
          <div className="w-2 h-16 bg-emerald-500 rounded-full" />
        </div>
      </div>
    </div>
  );
}
