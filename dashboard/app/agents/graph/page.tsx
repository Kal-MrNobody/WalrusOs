"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactFlow, {
  Background, Controls, MiniMap, MarkerType,
  useNodesState, useEdgesState, useReactFlow, ReactFlowProvider,
  type Node, type Edge, type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { ExternalLink, Network, X, Download } from "lucide-react";
import { api } from "@/lib/api";
import type { GraphNode, GraphEdge } from "@/lib/api";
import { TruncatedId } from "@/components/copy-button";
import { cn } from "@/lib/utils";

// ── Custom Node: Agent ────────────────────────────────────────────────────────

function AgentNode({ data }: NodeProps) {
  const statusColor =
    data.status === "active"     ? "bg-emerald-500" :
    data.status === "paused"     ? "bg-amber-500"   :
    data.status === "terminated" ? "bg-red-500"     : "bg-slate-500";

  return (
    <div className="rounded-xl border-2 border-violet-600/70 bg-slate-900 px-4 py-3 shadow-lg shadow-violet-900/20 min-w-[140px]">
      <div className="flex items-center gap-2 mb-1">
        <span className={cn("h-2 w-2 rounded-full shrink-0", statusColor)} />
        <span className="text-sm font-semibold text-violet-200 truncate max-w-[120px]">
          {data.label}
        </span>
      </div>
      <div className="text-[10px] text-slate-500 flex gap-2">
        <span>{data.event_count ?? 0} events</span>
        {data.execution_count != null && (
          <span>{data.execution_count} runs</span>
        )}
      </div>
    </div>
  );
}

// ── Custom Node: Stream ───────────────────────────────────────────────────────

function StreamNode({ data }: NodeProps) {
  return (
    <div className="rounded-xl border border-violet-800/50 bg-slate-900/80 px-4 py-3 shadow-md min-w-[120px]">
      <div className="flex items-center gap-1.5 mb-1">
        <div className="h-2 w-2 rounded-sm bg-violet-600/60" />
        <span className="text-xs font-medium text-slate-300 truncate max-w-[110px]">
          {data.label}
        </span>
      </div>
      <div className="text-[10px] text-slate-600">
        {data.event_count ?? 0} events
      </div>
    </div>
  );
}

const nodeTypes = { agent: AgentNode, stream: StreamNode };

// ── Layout helper: assign positions manually ──────────────────────────────────
// Agents on top row, streams on bottom. Spaced 220px horizontally.

function layoutNodes(rawNodes: GraphNode[]): Node[] {
  const agents  = rawNodes.filter(n => n.type === "agent");
  const streams = rawNodes.filter(n => n.type === "stream");

  const agentSpacing  = 220;
  const streamSpacing = 200;

  return [
    ...agents.map((n, i) => ({
      id:       n.id,
      type:     "agent",
      position: {
        x: i * agentSpacing - (agents.length - 1) * agentSpacing / 2,
        y: 0,
      },
      data: { ...n },
    })),
    ...streams.map((n, i) => ({
      id:       n.id,
      type:     "stream",
      position: {
        x: i * streamSpacing - (streams.length - 1) * streamSpacing / 2,
        y: 220,
      },
      data: { ...n },
    })),
  ];
}

function layoutEdges(rawEdges: GraphEdge[]): Edge[] {
  return rawEdges.map(e => ({
    id:           e.id,
    source:       e.source,
    target:       e.target,
    label:        e.count > 0 ? `${e.count}` : "",
    labelStyle:   { fill: "#94a3b8", fontSize: 10 },
    labelBgStyle: { fill: "#0f172a" },
    style:        { stroke: "#7c3aed", strokeWidth: 1.5 },
    markerEnd:    { type: MarkerType.ArrowClosed, color: "#7c3aed" },
    animated:     false,
  }));
}

// ── Detail Panel ──────────────────────────────────────────────────────────────

function DetailPanel({
  node,
  onClose,
}: {
  node: GraphNode;
  onClose: () => void;
}) {
  const isAgent = node.type === "agent";
  const suiUrl = node.sui_object_id
    ? `https://suiexplorer.com/object/${node.sui_object_id}?network=testnet`
    : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <span className={cn(
            "text-[10px] font-semibold uppercase tracking-widest",
            isAgent ? "text-violet-400" : "text-slate-400"
          )}>
            {isAgent ? "Agent" : "Stream"}
          </span>
          <h3 className="mt-0.5 text-base font-semibold text-slate-100">{node.label}</h3>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-slate-500">ID</span>
          <TruncatedId value={node.id} chars={12} className="text-slate-300" />
        </div>

        {isAgent && node.status && (
          <div className="flex justify-between">
            <span className="text-slate-500">Status</span>
            <span className={cn(
              "text-xs font-medium",
              node.status === "active" ? "text-emerald-400" :
              node.status === "paused" ? "text-amber-400" : "text-red-400"
            )}>
              {node.status}
            </span>
          </div>
        )}

        <div className="flex justify-between">
          <span className="text-slate-500">Events</span>
          <span className="text-slate-300">{node.event_count}</span>
        </div>

        {isAgent && node.execution_count != null && (
          <div className="flex justify-between">
            <span className="text-slate-500">Executions</span>
            <span className="text-slate-300">{node.execution_count}</span>
          </div>
        )}

        {isAgent && node.public_key && (
          <div>
            <span className="text-slate-500">Public Key</span>
            <p className="mt-1 break-all font-mono text-[10px] text-slate-400 rounded bg-slate-800 p-2">
              {node.public_key.slice(0, 48)}…
            </p>
          </div>
        )}

        {node.created_at && (
          <div className="flex justify-between">
            <span className="text-slate-500">Created</span>
            <span className="text-slate-400 text-xs">
              {new Date(node.created_at).toLocaleDateString()}
            </span>
          </div>
        )}
      </div>

      {suiUrl && (
        <a
          href={suiUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          View on Sui Explorer
        </a>
      )}
    </div>
  );
}

// ── Inner graph component (needs ReactFlowProvider context) ───────────────────

function GraphCanvas({
  rawNodes,
  rawEdges,
}: {
  rawNodes: GraphNode[];
  rawEdges: GraphEdge[];
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes(rawNodes));
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges(rawEdges));
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const { fitView } = useReactFlow();

  // Re-layout when data arrives
  useEffect(() => {
    setNodes(layoutNodes(rawNodes));
    setEdges(layoutEdges(rawEdges));
    setTimeout(() => fitView({ padding: 0.3 }), 50);
  }, [rawNodes, rawEdges]); // eslint-disable-line

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const gn = rawNodes.find(n => n.id === node.id);
    setSelected(gn ?? null);
  }, [rawNodes]);

  // Export as PNG
  const exportPng = useCallback(() => {
    const svg = document.querySelector(".react-flow__renderer svg") as SVGElement | null;
    if (!svg) return;
    const data = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([data], { type: "image/svg+xml" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = "agent-graph.svg";
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  return (
    <div className="relative flex gap-4 h-full">
      <div className="flex-1 rounded-xl border border-slate-800 overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          minZoom={0.3}
          maxZoom={2}
          style={{ background: "#020617" }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls className="[&>button]:bg-slate-800 [&>button]:border-slate-700 [&>button]:text-slate-300" />
          <MiniMap
            nodeColor={n => n.type === "agent" ? "#7c3aed" : "#334155"}
            maskColor="rgba(2,6,23,0.7)"
            style={{ background: "#0f172a", border: "1px solid #1e293b" }}
          />
        </ReactFlow>

        {/* Controls overlay */}
        <div className="absolute top-3 right-3 flex gap-2 z-10">
          <button
            onClick={() => fitView({ padding: 0.3 })}
            className="rounded border border-slate-700 bg-slate-900/90 px-2.5 py-1.5 text-xs
                       text-slate-300 hover:border-violet-600/50 hover:text-violet-300 transition-colors"
          >
            Fit View
          </button>
          <button
            onClick={() => { setNodes(layoutNodes(rawNodes)); setEdges(layoutEdges(rawEdges)); setTimeout(() => fitView({ padding: 0.3 }), 50); }}
            className="rounded border border-slate-700 bg-slate-900/90 px-2.5 py-1.5 text-xs
                       text-slate-300 hover:border-slate-500 transition-colors"
          >
            Reset
          </button>
          <button
            onClick={exportPng}
            className="rounded border border-slate-700 bg-slate-900/90 p-1.5
                       text-slate-400 hover:text-slate-200 transition-colors"
            title="Export as SVG"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Detail panel */}
      {selected && (
        <div className="w-72 shrink-0 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <DetailPanel node={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AgentGraphPage() {
  const [rawNodes, setRawNodes] = useState<GraphNode[]>([]);
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [mounted, setMounted]   = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    api.graph.get()
      .then(d => { setRawNodes(d.nodes); setRawEdges(d.edges); })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col gap-4" style={{ height: "calc(100vh - 80px)" }}>
      <div className="flex items-center justify-between border-b border-slate-800 pb-4 shrink-0">
        <div className="flex items-center gap-3">
          <Network className="h-6 w-6 text-violet-400" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Agent Graph</h1>
            <p className="text-sm text-slate-500">
              {rawNodes.filter(n => n.type === "agent").length} agents ·{" "}
              {rawNodes.filter(n => n.type === "stream").length} streams ·{" "}
              {rawEdges.length} connections
            </p>
          </div>
        </div>
        <div className="flex gap-2 text-xs text-slate-600">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-violet-600" /> Agent
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm border border-violet-800/50 bg-slate-900/80" /> Stream
          </span>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-400 shrink-0">
          {error} —{" "}
          <button onClick={() => window.location.reload()} className="underline">Retry</button>
        </div>
      )}

      {loading && (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
          <div className="flex flex-col items-center gap-3">
            <div className="flex gap-1.5">
              {[0,1,2].map(i => (
                <div key={i} className="h-2 w-2 rounded-full bg-violet-600 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
            Loading agent graph…
          </div>
        </div>
      )}

      {!loading && !error && rawNodes.length === 0 && (
        <div className="flex flex-1 flex-col items-center justify-center text-slate-600">
          <Network className="mb-3 h-10 w-10 opacity-25" />
          <p className="text-sm">No agents registered yet.</p>
          <p className="mt-1 text-xs">Run the demo to populate: <code className="font-mono">python scripts/demo_recovery.py</code></p>
        </div>
      )}

      {!loading && mounted && rawNodes.length > 0 && (
        <div className="flex-1 min-h-0">
          <ReactFlowProvider>
            <GraphCanvas rawNodes={rawNodes} rawEdges={rawEdges} />
          </ReactFlowProvider>
        </div>
      )}
    </div>
  );
}
