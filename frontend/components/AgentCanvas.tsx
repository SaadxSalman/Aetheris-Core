"use client";
/* Live agent-graph telemetry canvas (React Flow). */
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import clsx from "clsx";
import {
  Box,
  Crosshair,
  Globe,
  MessageSquare,
  Route,
  ScanSearch,
  Search,
  ShieldCheck,
  Sparkles,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { useMemo } from "react";
import type { AgentNodeKey, NodeInfo } from "@/lib/types";
import { StatusDot } from "./ui";

interface LayoutDef {
  x: number;
  y: number;
  label: string;
  sub: string;
  icon: LucideIcon;
}

const LAYOUT: Record<AgentNodeKey, LayoutDef> = {
  query: { x: 0, y: 250, label: "User Query", sub: "SSE ingress", icon: MessageSquare },
  intent_router: { x: 260, y: 250, label: "Intent Router", sub: "semantic dispatch", icon: Route },
  web_fallback: { x: 545, y: -30, label: "Web Fallback", sub: "Tavily · SerpAPI · DDG", icon: Globe },
  retrieve: { x: 545, y: 250, label: "Hybrid Retrieval", sub: "BM25 + dense + PPR", icon: Search },
  reformulate: { x: 545, y: 520, label: "Reformulate", sub: "query rewrite loop", icon: Wand2 },
  rerank: { x: 830, y: 250, label: "Cross-Encoder", sub: "rerank top-k", icon: ScanSearch },
  grade: { x: 1110, y: 250, label: "CRAG Grader", sub: "confidence gate", icon: ShieldCheck },
  verify_grounding: { x: 1400, y: 250, label: "Grounding Check", sub: "aspect support", icon: Crosshair },
  generate: { x: 1690, y: 250, label: "Generator", sub: "streamed + cited", icon: Sparkles },
  answer: { x: 1975, y: 250, label: "Answer", sub: "attested citations", icon: Box },
};

type EdgeKind = "main" | "pass" | "fail" | "loop" | "repair";

interface EdgeDef {
  id: string;
  source: AgentNodeKey;
  target: AgentNodeKey;
  kind: EdgeKind;
  label?: string;
}

const EDGE_DEFS: EdgeDef[] = [
  { id: "e-q", source: "query", target: "intent_router", kind: "main" },
  { id: "e-r", source: "intent_router", target: "retrieve", kind: "main" },
  { id: "e-ret", source: "retrieve", target: "rerank", kind: "main" },
  { id: "e-rk", source: "rerank", target: "grade", kind: "main" },
  { id: "e-pass", source: "grade", target: "verify_grounding", kind: "pass", label: "pass" },
  { id: "e-fail", source: "grade", target: "reformulate", kind: "fail", label: "fail · rewrite" },
  { id: "e-web", source: "grade", target: "web_fallback", kind: "fail", label: "exhausted" },
  { id: "e-loop", source: "reformulate", target: "retrieve", kind: "loop", label: "re-query" },
  { id: "e-wloop", source: "web_fallback", target: "retrieve", kind: "loop", label: "merge" },
  { id: "e-repair", source: "verify_grounding", target: "reformulate", kind: "repair", label: "repair" },
  { id: "e-ground", source: "verify_grounding", target: "generate", kind: "pass", label: "grounded" },
  { id: "e-stream", source: "generate", target: "answer", kind: "main", label: "stream" },
];

const KIND_COLOR: Record<EdgeKind, string> = {
  main: "#22d3ee",
  pass: "#34d399",
  fail: "#fbbf24",
  loop: "#a78bfa",
  repair: "#fbbf24",
};

function AgentNode({ data }: { data: any }) {
  const info: NodeInfo = data.info ?? { status: "idle" };
  const Icon: LucideIcon = data.icon;
  const border =
    info.status === "running"
      ? "border-cyan-400/70"
      : info.status === "success"
        ? "border-emerald-500/45"
        : info.status === "failed"
          ? "border-rose-500/55"
          : "border-slate-700/60";
  const iconBg =
    info.status === "success"
      ? "bg-emerald-500/15 text-emerald-300"
      : info.status === "failed"
        ? "bg-rose-500/15 text-rose-300"
        : info.status === "running"
          ? "bg-cyan-500/20 text-cyan-300"
          : "bg-slate-800 text-slate-400";
  return (
    <div
      className={clsx(
        "relative w-[228px] rounded-xl border bg-gradient-to-b from-slate-900 to-slate-950/95 px-3 py-2.5 shadow-xl shadow-black/40 transition-all",
        border,
        info.status === "running" && "node-running",
        info.status === "idle" && "opacity-60",
      )}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center gap-2.5">
        <span className={clsx("rounded-md p-1.5", iconBg)}>
          <Icon size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-slate-100">{data.label}</div>
          <div className="truncate text-[10px] text-slate-500">{data.sub}</div>
        </div>
        <StatusDot status={info.status} />
      </div>
      {info.badge && (
        <div className="mt-2 truncate rounded-md border border-cyan-500/25 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300">
          {info.badge}
        </div>
      )}
      {info.detail && (
        <div className="mt-1 truncate text-[10px] leading-tight text-slate-500" title={info.detail}>
          {info.detail}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

function isActive(def: EdgeDef, nodes: Record<AgentNodeKey, NodeInfo>): boolean {
  const s = nodes[def.source];
  const t = nodes[def.target];
  if (!s || !t) return false;
  const srcLive = s.status === "running" || s.status === "success" || s.status === "failed";
  const tgtLive = t.status === "running" || t.status === "success";
  return srcLive && tgtLive;
}

export default function AgentCanvas({
  nodes,
}: {
  nodes: Record<AgentNodeKey, NodeInfo>;
}) {
  const rfNodes: Node[] = useMemo(
    () =>
      (Object.keys(LAYOUT) as AgentNodeKey[]).map((key) => {
        const def = LAYOUT[key];
        return {
          id: key,
          type: "agent",
          position: { x: def.x, y: def.y },
          data: { ...def, info: nodes[key] },
        };
      }),
    [nodes],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      EDGE_DEFS.map((def) => {
        const active = isActive(def, nodes);
        const color = KIND_COLOR[def.kind];
        return {
          id: def.id,
          source: def.source,
          target: def.target,
          type: "smoothstep",
          label: def.label,
          labelStyle: { fill: "#94a3b8", fontSize: 10, fontWeight: 600 },
          labelBgStyle: { fill: "#0b1220", fillOpacity: 0.9 },
          labelBgPadding: [6, 3],
          animated: active,
          className: active ? "edge-active" : undefined,
          style: {
            stroke: active ? color : "rgba(148,163,184,0.28)",
            strokeWidth: active ? 2.4 : 1.4,
            opacity: active ? 1 : 0.75,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: active ? color : "rgba(148,163,184,0.4)",
          },
        };
      }),
    [nodes],
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1.05 }}
        minZoom={0.25}
        maxZoom={1.8}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={22} color="rgba(148,163,184,0.09)" size={1.4} />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => {
            const st = nodes[n.id as AgentNodeKey]?.status;
            return st === "running"
              ? "#22d3ee"
              : st === "success"
                ? "#34d399"
                : st === "failed"
                  ? "#f43f5e"
                  : "#334155";
          }}
          maskColor="rgba(2,6,23,0.75)"
          style={{ width: 150, height: 100 }}
        />
      </ReactFlow>
    </div>
  );
}

