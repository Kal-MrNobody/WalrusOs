"use client";

import { Explainer } from "@/components/explainer";
import { Shield } from "lucide-react";

export default function CapabilitiesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Shield className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Capabilities</h1>
      </div>

      <Explainer title="Internal Mechanics: Object Capabilities (OCaps)">
        <p>
          WalrusOS enforces access control using Sui's native Object-Capability model. 
          Instead of Access Control Lists (ACLs), permissions are literal digital assets owned by the Agent's wallet. 
          For example, to write to a stream, the agent must physically own an <code>AppendCapability</code> object 
          on the blockchain. This makes permissions provably secure, transferable, and revocable.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50">
        <table className="w-full text-left text-sm text-slate-400">
          <thead className="bg-slate-950 text-xs uppercase">
            <tr>
              <th className="px-6 py-3">Agent</th>
              <th className="px-6 py-3">Capability Type</th>
              <th className="px-6 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-800">
              <td className="px-6 py-4 text-slate-200">ResearchAgent</td>
              <td className="px-6 py-4 font-mono text-violet-400">AppendCapability</td>
              <td className="px-6 py-4 text-emerald-400">Granted</td>
            </tr>
            <tr className="border-t border-slate-800">
              <td className="px-6 py-4 text-slate-200">ReviewerAgent</td>
              <td className="px-6 py-4 font-mono text-violet-400">AdminCapability</td>
              <td className="px-6 py-4 text-rose-400">Revoked</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
