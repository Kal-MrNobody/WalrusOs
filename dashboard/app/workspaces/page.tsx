"use client";

import { Explainer } from "@/components/explainer";
import { LayoutDashboard } from "lucide-react";

export default function WorkspacesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <LayoutDashboard className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Workspace Graph</h1>
      </div>

      <Explainer title="Internal Mechanics: Workspaces as Boundaries">
        <p>
          In WalrusOS, a <strong>Workspace</strong> isn't just a folder—it's a cryptographic boundary on the Sui blockchain. 
          When a workspace is created, a unique Sui Object is deployed. This object acts as the root 
          for all Object-Capabilities (OCaps). Agents within a workspace can only share capabilities and 
          verify events that are anchored to this specific Workspace ID.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="grid gap-4 md:grid-cols-2">
        {["default", "research-lab", "production-cluster"].map((ws) => (
          <div key={ws} className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <h3 className="font-semibold text-slate-200">{ws}</h3>
            <div className="mt-2 flex items-center gap-2 text-sm text-slate-500">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Sui Object: 0x...{Math.random().toString(16).slice(2, 6)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
