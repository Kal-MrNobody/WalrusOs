"use client";

import { Explainer } from "@/components/explainer";
import { ShieldCheck } from "lucide-react";

export default function VerificationPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <ShieldCheck className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Verification</h1>
      </div>

      <Explainer title="Internal Mechanics: Cryptographic Signatures">
        <p>
          You cannot fake memory in WalrusOS. During read operations, the <strong>ValidationEngine</strong> 
          enforces strict integrity constraints. It computes the SHA-256 hash of the canonical JSON payload, 
          and then verifies that hash against the attached Ed25519 signature using the agent's known public key. 
          If a single byte is modified locally or in transit, the signature check fails and the event is rejected.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="font-semibold text-emerald-200">Live Verification Log</div>
          <div className="text-xs font-mono text-emerald-500 bg-emerald-950 px-2 py-1 rounded">Ed25519</div>
        </div>
        <div className="space-y-2 font-mono text-xs">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex gap-4 text-slate-400 border-t border-emerald-900/30 pt-2">
              <span className="text-slate-500">2026-06-17 14:02:{30+i}</span>
              <span className="text-emerald-400">PASS</span>
              <span>Event {Math.random().toString(16).slice(2, 10)}</span>
              <span className="truncate flex-1">Signature matched expected hash</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
