"use client";

import { useCallback } from "react";
import ReactFlow, {
  Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  BackgroundVariant,
  type Node, type Edge,
} from "reactflow";
import "reactflow/dist/style.css";
import type { GraphData } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  active: "#8b5cf6",
  idle:   "#475569",
};

interface Props { graph: GraphData }

export function AgentGraphView({ graph }: Props) {
  const radius = 200;
  const cx = 300, cy = 250;

  const initialNodes: Node[] = graph.nodes.map((n, i) => {
    const angle = (i / graph.nodes.length) * 2 * Math.PI - Math.PI / 2;
    return {
      id: n.id,
      data: { label: n.label },
      position: {
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      },
      style: {
        background: "#1e293b",
        border: `2px solid ${STATUS_COLOR[n.status ?? ""] ?? "#475569"}`,
        color: "#e2e8f0",
        borderRadius: "12px",
        padding: "10px 18px",
        fontSize: "13px",
        fontWeight: 600,
      },
    };
  });

  const initialEdges: Edge[] = graph.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    label: e.label,
    animated: true,
    style: { stroke: "#8b5cf6", strokeWidth: 2 },
    labelStyle: { fill: "#a78bfa", fontSize: 11 },
    labelBgStyle: { fill: "#1e1b4b" },
  }));

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  return (
    <div className="h-[520px] rounded-xl overflow-hidden border border-slate-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} color="#334155" gap={20} />
        <Controls className="[&>button]:bg-slate-800 [&>button]:border-slate-700 [&>button]:text-slate-300" />
        <MiniMap
          nodeColor={(n) => STATUS_COLOR[(n.data as { status?: string }).status ?? ""] ?? "#475569"}
          className="!bg-slate-900 !border-slate-800"
        />
      </ReactFlow>
    </div>
  );
}
