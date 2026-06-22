"use client";

import { useEffect, useRef, useState } from "react";

interface LiveEvent {
  id: string;
  type: string;
  stream: string;
  agent: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

const TYPE_COLOR: Record<string, string> = {
  "MemoryAppended":    "bg-violet-500/20 text-violet-300 border-violet-500/30",
  "AgentRegistered":   "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  "MemoryForked":      "bg-amber-500/20  text-amber-300  border-amber-500/30",
  "MemoryMerged":      "bg-orange-500/20 text-orange-300 border-orange-500/30",
  "CapabilityGranted": "bg-sky-500/20    text-sky-300    border-sky-500/30",
  "ValidationFailed":  "bg-red-500/20    text-red-300    border-red-500/30",
};

export function EventFeed() {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8787/ws/events");
    wsRef.current = ws;
    ws.onopen  = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const ev: LiveEvent = JSON.parse(e.data);
      setEvents((prev) => [ev, ...prev].slice(0, 100));
    };
    return () => ws.close();
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
        <span className="text-sm text-slate-400">{connected ? "Connected" : "Disconnected"}</span>
        <span className="ml-auto text-xs text-slate-600">{events.length} events received</span>
      </div>

      <div className="flex flex-col gap-2 max-h-[70vh] overflow-y-auto pr-1">
        {events.map((ev) => (
          <div key={ev.id} className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm">
            <div className="flex items-center gap-2 mb-1">
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${TYPE_COLOR[ev.type] ?? "bg-slate-700 text-slate-300"}`}>
                {ev.type}
              </span>
              <span className="text-slate-500 text-xs">{new Date(ev.timestamp).toLocaleTimeString()}</span>
            </div>
            <div className="text-slate-300">
              <span className="text-violet-400">{ev.agent}</span>
              {" → "}
              <span className="text-emerald-400">{ev.stream}</span>
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <p className="text-slate-600 text-sm text-center py-8">Waiting for events…</p>
        )}
      </div>
    </div>
  );
}
