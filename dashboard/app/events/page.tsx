"use client";

import { Explainer } from "@/components/explainer";
import { Radio } from "lucide-react";

export default function EventsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Radio className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Protocol Events</h1>
      </div>

      <Explainer title="Internal Mechanics: The Immutable Ledger">
        <p>
          A <strong>ProtocolEvent</strong> is the fundamental unit of WalrusOS. Every change—whether an agent writes memory, 
          a capability is granted, or a stream is branched—is serialized into canonical JSON. 
          We hash this JSON, sign it with the agent's Ed25519 key, and append it. 
          Because every event references a <code>parent_hash</code>, the entire protocol forms an immutable Directed Acyclic Graph (DAG).
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="rounded-lg border border-slate-800 bg-black/50 p-4 overflow-x-auto">
        <pre className="text-xs font-mono text-emerald-400/90">
{`{
  "event_id": "83f2e12d7dd39e8a...",
  "event_type": "MemoryAppended",
  "parent_hash": "c554f24e70499b1f...",
  "signature": "Ed25519:3dfcb323a8...",
  "payload": {
    "thought": "Found interesting metrics.",
    "latency_ms": 400
  }
}`}
        </pre>
      </div>
    </div>
  );
}
