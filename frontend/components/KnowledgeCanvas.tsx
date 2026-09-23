"use client";
/* Secondary canvas: the extracted knowledge graph (entities + typed edges). */
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { Network } from "lucide-react";
import { useMemo } from "react";
import type { KnowledgeGraph } from "@/lib/types";
import { Badge, Card } from "./ui";

const TYPE_COLOR: Record<string, string> = {
  component: "#22d3ee",
  datastore: "#a78bfa",
  model: "#f472b6",
  process: "#fbbf24",
  artifact: "#34d399",
  actor: "#60a5fa",
  concept: "#94a3b8",
};

export default function KnowledgeCanvas({ data }: { data: KnowledgeGraph | null }) {
  const { rfNodes, rfEdges } = useMemo(() => {
    if (!data || data.nodes.length === 0) {
      return { rfNodes: [] as Node[], rfEdges: [] as Edge[] };
    }
    const n = data.nodes.length;
    const radiusX = Math.max(340, n * 14);
    const radiusY = Math.max(230, n * 8.5);
    const center = { x: radiusX + 80, y: radiusY + 60 };
    const nodes: Node[] = data.nodes.map((ent, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2;
      const color = TYPE_COLOR[ent.type] ?? TYPE_COLOR.concept;
      return {
        id: ent.id,
        position: {
          x: center.x + radiusX * Math.cos(angle),
          y: center.y + radiusY * Math.sin(angle),
        },
        data: {
          label: `${ent.label}  ·  ${ent.mentions}`,
        },
        style: {
          background: "#0b1220",
          color,
          border: `1px solid ${color}66`,
          borderRadius: 999,
          padding: "4px 10px",
          fontSize: 10.5,
          fontWeight: 600,
          boxShadow: `0 0 14px ${color}22`,
        },
      };
    });
    const edges: Edge[] = data.edges.map((rel) => ({
      id: rel.id,
      source: rel.source,
      target: rel.target,
      label: rel.type,
      labelStyle: { fill: "#64748b", fontSize: 8 },
      labelBgStyle: { fill: "#0b1220", fillOpacity: 0.85 },
      labelBgPadding: [4, 2],
      style: { stroke: "rgba(148,163,184,0.3)", strokeWidth: Math.min(rel.weight, 3) },
      markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: "#475569" },
    }));
    return { rfNodes: nodes, rfEdges: edges };
  }, [data]);

  return (
    <Card
      title="Knowledge Graph"
      icon={Network}
      className="h-full"
      actions={
        <>
          <Badge tone="cyan">{data?.nodes.length ?? 0} entities</Badge>
          <Badge tone="violet">{data?.edges.length ?? 0} edges</Badge>
          <Badge tone="amber">{data?.communities.length ?? 0} communities</Badge>
        </>
      }
      bodyClassName="p-0"
    >
      {!data || data.nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center text-[11px] text-slate-600">
          The knowledge graph is empty — ingest documents to populate it.
        </div>
      ) : (
        <div className="h-full w-full">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.15}
            maxZoom={2}
            nodesDraggable
            nodesConnectable={false}
            elementsSelectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={22} color="rgba(148,163,184,0.08)" size={1.4} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}
    </Card>
  );
}
