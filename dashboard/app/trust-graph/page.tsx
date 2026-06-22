"use client";

import { Explainer } from "@/components/explainer";
import { Activity } from "lucide-react";

export default function TrustGraphPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
        <Activity className="h-6 w-6 text-violet-400" />
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">Trust Graph</h1>
      </div>

      <Explainer title="Internal Mechanics: Cryptographic Reputation">
        <p>
          Because WalrusOS uses Event Sourcing, reputation can be mathematically calculated. 
          Every time an agent successfully appends a verified event, or validates another agent's event, 
          their <strong>TrustRoot</strong> (a rolling hash of their verified actions) increments. 
          The Trust Graph allows developers to see which agents are producing valid, high-quality protocol actions over time.
        </p>
      </Explainer>

      {/* Mock UI */}
      <div className="grid gap-4 md:grid-cols-3">
        {["ResearchAgent", "ReviewerAgent", "WriterAgent"].map((agent) => (
          <div key={agent} className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <h3 className="font-semibold text-slate-200">{agent}</h3>
            <div className="mt-4 flex flex-col gap-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">Trust Score</span>
                <span className="text-emerald-400 font-mono">{(Math.random() * 100).toFixed(2)}</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800">
                <div className="h-full rounded-full bg-violet-500" style={{ width: `${Math.random() * 100}%` }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
