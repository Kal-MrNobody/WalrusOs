"use client";

import { Explainer } from "@/components/explainer";
import { Database } from "lucide-react";

export default function WalrusPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Database className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Walrus Blobs</h1>
      </div>

      <Explainer title="Internal Mechanics: DSN Storage">
        <p>
          Blockchains are too expensive for storing raw AI payloads (like 100kb context windows or artifacts). 
          Instead, the <code>EventStore</code> engine uploads the canonical JSON payload directly to the 
          <strong>Walrus Decentralized Storage Network (DSN)</strong>. Walrus returns a cryptographic <code>Blob ID</code>, 
          and only that lightweight ID is anchored to the Sui blockchain.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="grid gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 rounded bg-slate-800 flex items-center justify-center font-mono text-xs text-slate-400">BLB</div>
              <div>
                <div className="font-mono text-sm text-slate-200">w{Math.random().toString(16).slice(2, 12)}...</div>
                <div className="text-xs text-slate-500">Epoch 142 • Size: 2.4kb</div>
              </div>
            </div>
            <button className="text-xs text-violet-400 hover:text-violet-300">View Payload</button>
          </div>
        ))}
      </div>
    </div>
  );
}
