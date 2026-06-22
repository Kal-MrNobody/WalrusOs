"use client";

import { Explainer } from "@/components/explainer";
import { Package } from "lucide-react";

export default function SuiPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Package className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Sui Objects</h1>
      </div>

      <Explainer title="Internal Mechanics: Move Contracts">
        <p>
          WalrusOS runs a highly optimized Move Smart Contract on the Sui Network. The core modules 
          (<code>memory.move</code>, <code>identity.move</code>, <code>permissions.move</code>) manage the 
          lifecycle of the protocol. Every Agent, Workspace, and Stream is represented as an owned Object on-chain. 
          When an agent appends an event, a transaction emits an <code>EventAnchored</code> log containing the Blob ID.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          <h3 className="font-semibold text-slate-200 mb-4">memory.move</h3>
          <pre className="text-xs font-mono text-slate-400 bg-slate-950 p-3 rounded border border-slate-800">
{`struct Stream has key, store {
    id: UID,
    workspace_id: ID,
    owner: address,
    head_event_hash: vector<u8>,
}`}
          </pre>
        </div>
      </div>
    </div>
  );
}
