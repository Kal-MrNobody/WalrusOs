"use client";

import { useCallback, useRef, useState } from "react";
import { DatabaseBackup, CheckCircle2, Circle, Loader2, Play, Terminal, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

const BASE = process.env.NEXT_PUBLIC_BRIDGE_URL ?? "http://localhost:8787";

// ── Step definitions ──────────────────────────────────────────────────────────

type StepStatus = "idle" | "running" | "done" | "error";

interface Step {
  id:       string;
  label:    string;
  detail:   string;
  keywords: string[];
}

const STEPS: Step[] = [
  { id: "build",   label: "Build",   detail: "Register agent identity on Sui, write memory events to Walrus",
    keywords: ["build", "register", "agent", "identity", "write", "upload"] },
  { id: "destroy", label: "Destroy", detail: "Wipe local SQLite cache, forget all in-memory state",
    keywords: ["destroy", "wipe", "clear", "delete", "local"] },
  { id: "recover", label: "Recover", detail: "Re-index from Sui events, download blobs from Walrus",
    keywords: ["recover", "reconstruct", "download", "re-index", "replay"] },
  { id: "verify",  label: "Verify",  detail: "Verify Ed25519 signatures, assert event count matches",
    keywords: ["verify", "check", "assert", "signature", "valid"] },
];

// ── Step diagram ──────────────────────────────────────────────────────────────

function StepDiagram({ statuses }: { statuses: Record<string, StepStatus> }) {
  return (
    <div className="flex flex-wrap items-center gap-0">
      {STEPS.map((step, idx) => {
        const status = statuses[step.id] ?? "idle";
        return (
          <div key={step.id} className="flex items-center">
            <div className={cn(
              "flex flex-col items-center gap-2 rounded-xl border p-4 w-40 transition-all duration-300",
              status === "running" && "border-violet-600 bg-violet-900/20",
              status === "done"    && "border-emerald-700 bg-emerald-900/10",
              status === "error"   && "border-red-700 bg-red-900/10",
              status === "idle"    && "border-slate-800 bg-slate-900/40",
            )}>
              <div className={cn(
                "flex h-10 w-10 items-center justify-center rounded-full border-2",
                status === "idle"    && "border-slate-700 bg-slate-900 text-slate-600",
                status === "running" && "border-violet-500 bg-violet-900/40 text-violet-400",
                status === "done"    && "border-emerald-600 bg-emerald-900/30 text-emerald-400",
                status === "error"   && "border-red-600 bg-red-900/30 text-red-400",
              )}>
                {status === "running" && <Loader2 className="h-5 w-5 animate-spin" />}
                {status === "done"    && <CheckCircle2 className="h-5 w-5" />}
                {status === "idle"    && <Circle className="h-5 w-5" />}
                {status === "error"   && <span className="text-sm font-bold">!</span>}
              </div>
              <span className={cn("text-sm font-semibold",
                status === "idle"    && "text-slate-600",
                status === "running" && "text-violet-300",
                status === "done"    && "text-emerald-400",
                status === "error"   && "text-red-400",
              )}>{step.label}</span>
              <p className="text-center text-[10px] text-slate-600 leading-snug">{step.detail}</p>
            </div>
            {idx < STEPS.length - 1 && (
              <ChevronRight className={cn("h-5 w-5 mx-1 shrink-0",
                statuses[STEPS[idx + 1].id] === "idle" ? "text-slate-800" : "text-violet-600")} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RecoveryPage() {
  const [running, setRunning]   = useState(false);
  const [lines, setLines]       = useState<string[]>([]);
  const [statuses, setStatuses] = useState<Record<string, StepStatus>>({});
  const [done, setDone]         = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  function detectStep(line: string): string | null {
    const lower = line.toLowerCase();
    for (const step of STEPS) {
      if (step.keywords.some(k => lower.includes(k))) return step.id;
    }
    return null;
  }

  const runRecovery = useCallback(async () => {
    setRunning(true);
    setLines([]);
    setStatuses({});
    setDone(false);

    let res: Response;
    try {
      res = await fetch(`${BASE}/api/recovery/run`);
    } catch (e) {
      setLines([`Error: ${e}`]);
      setRunning(false);
      return;
    }
    if (!res.body) { setRunning(false); return; }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";
    let activeStep: string | null = null;

    while (true) {
      const { done: streamDone, value } = await reader.read();
      if (streamDone) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        if (!part.trim()) continue;
        const text = part.startsWith("data: ") ? part.slice(6) : part;
        if (!text) continue;

        setLines(prev => {
          const next = [...prev, text];
          setTimeout(() => logRef.current?.scrollTo({ top: 99999, behavior: "smooth" }), 50);
          return next;
        });

        const stepId = detectStep(text);
        if (stepId && stepId !== activeStep) {
          if (activeStep) setStatuses(prev => ({ ...prev, [activeStep!]: "done" }));
          activeStep = stepId;
          setStatuses(prev => ({ ...prev, [stepId]: "running" }));
        }
      }
    }

    if (activeStep) setStatuses(prev => ({ ...prev, [activeStep!]: "done" }));
    setRunning(false);
    setDone(true);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <DatabaseBackup className="h-6 w-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Recovery Demo</h1>
            <p className="text-sm text-slate-500">
              Prove stateless recovery: wipe SQLite, reconstruct from Sui + Walrus alone
            </p>
          </div>
        </div>
        <button
          onClick={runRecovery}
          disabled={running}
          className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium
                     text-white hover:bg-violet-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {running
            ? <><Loader2 className="h-4 w-4 animate-spin" /> Running…</>
            : <><Play className="h-4 w-4" /> Run Recovery</>}
        </button>
      </div>

      {/* Step diagram */}
      <div className="overflow-x-auto pb-2">
        <StepDiagram statuses={statuses} />
      </div>

      {/* Done banner */}
      {done && (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-700 bg-emerald-900/20 px-5 py-4">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-emerald-400">Recovery Complete</p>
            <p className="text-xs text-emerald-700 mt-0.5">
              Agent state reconstructed from the decentralized network. No local database required.
            </p>
          </div>
        </div>
      )}

      {/* Log terminal */}
      {(lines.length > 0 || running) && (
        <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-900/60 px-4 py-2.5">
            <Terminal className="h-3.5 w-3.5 text-slate-500" />
            <span className="text-xs font-medium text-slate-500">demo_recovery.py</span>
            {running && (
              <span className="ml-auto flex items-center gap-1.5 text-xs text-violet-400">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-pulse" />
                streaming
              </span>
            )}
          </div>
          <div ref={logRef} className="max-h-80 overflow-y-auto p-4 font-mono text-[12px] leading-relaxed space-y-0.5">
            {lines.map((line, i) => {
              const isErr  = /error|fail|exception/i.test(line);
              const isOk   = /success|ok|verified|done|complete/i.test(line);
              const isInfo = /^\[?info|step|===|---/i.test(line);
              return (
                <p key={i} className={cn(
                  isErr  ? "text-red-400"     :
                  isOk   ? "text-emerald-400" :
                  isInfo ? "text-violet-400"  : "text-slate-400"
                )}>
                  {line}
                </p>
              );
            })}
            {running && <p className="text-slate-600 animate-pulse">▊</p>}
          </div>
        </div>
      )}

      {/* Idle hint */}
      {!running && lines.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 gap-4 text-slate-700">
          <DatabaseBackup className="h-12 w-12" />
          <div className="text-center">
            <p className="text-sm">
              Click <span className="text-violet-500">Run Recovery</span> to start the demo.
            </p>
            <p className="text-xs mt-1">
              Runs <code className="bg-slate-900 rounded px-1">scripts/demo_recovery.py</code> and streams output live.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
