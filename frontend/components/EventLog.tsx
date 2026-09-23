"use client";
/* Chronological SSE telemetry log with type coloring. */
import clsx from "clsx";
import { ScrollText } from "lucide-react";
import { useEffect, useRef } from "react";
import type { UiEvent } from "@/lib/types";
import { Card } from "./ui";

function tone(type: string): string {
  if (type.startsWith("node_")) return "text-slate-500";
  if (type === "route_selected") return "text-violet-300";
  if (type === "retrieval_fusion" || type === "chunk_retrieved") return "text-cyan-300";
  if (type === "rerank_complete") return "text-sky-300";
  if (type === "chunk_graded") return "text-slate-400";
  if (type === "grade_result") return "text-emerald-300";
  if (type === "query_reformulated") return "text-amber-300";
  if (type === "web_fallback") return "text-orange-300";
  if (type === "grounding_check" || type === "grounding_audit") return "text-teal-300";
  if (type === "sql_result" || type === "graph_context") return "text-fuchsia-300";
  if (type === "answer") return "text-emerald-200";
  if (type === "error") return "text-rose-400";
  if (type === "run_start" || type === "run_end") return "text-slate-300 font-semibold";
  return "text-slate-400";
}

export default function EventLog({ events }: { events: UiEvent[] }) {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [events.length]);

  return (
    <Card
      title="Telemetry Stream"
      icon={ScrollText}
      actions={
        <span className="font-mono text-[10px] text-slate-500">{events.length} events</span>
      }
      bodyClassName="p-1.5"
    >
      <div className="font-mono text-[10.5px] leading-relaxed">
        {events.length === 0 && (
          <p className="p-4 text-center text-slate-600">
            Waiting for an agent run — every node transition streams here.
          </p>
        )}
        {events.map((ev, i) => (
          <div
            key={`${ev.seq ?? i}-${i}`}
            className="flex items-start gap-2 rounded px-1.5 py-[3px] hover:bg-slate-800/40"
          >
            <span className="w-[52px] shrink-0 text-right text-slate-600">
              {ev.elapsed_ms != null ? `${Math.round(ev.elapsed_ms)}ms` : ""}
            </span>
            <span className={clsx("w-[132px] shrink-0 truncate", tone(ev.type))}>
              {ev.type}
            </span>
            <span className="min-w-0 flex-1 truncate text-slate-500" title={JSON.stringify(ev.payload ?? {})}>
              {summarize(ev)}
            </span>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </Card>
  );
}

function summarize(ev: UiEvent): string {
  const p = ev.payload ?? {};
  switch (ev.type) {
    case "route_selected":
      return `route=${p.route} seeds=${(p.seeds ?? []).join(",") || "-"}`;
    case "retrieval_fusion":
      return `fused=${p.fused} counts=${JSON.stringify(p.counts)}`;
    case "chunk_retrieved":
      return `#${p.rank} ${p.chunk_id} · ${p.title}`;
    case "rerank_complete":
      return `${p.provider} → top ${p.top_k}`;
    case "chunk_graded":
      return `${p.accepted ? "ACCEPT" : "REJECT"} ${p.chunk_id} · ${p.reason}`;
    case "grade_result":
      return `conf=${p.confidence} thr=${p.threshold} passed=${p.passed}`;
    case "query_reformulated":
      return `#${p.attempt} ${p.strategy}: "${p.after}"`;
    case "web_fallback":
      return p.skipped ? "skipped" : `${p.provider}: ${p.count} results (${p.reason})`;
    case "grounding_check":
      return `score=${p.score} passed=${p.passed} — ${p.note}`;
    case "grounding_audit":
      return `${(p.support_ratio * 100).toFixed(0)}% of sentences supported`;
    case "sql_result":
      return `${p.label}: ${p.rows} rows`;
    case "graph_context":
      return p.mode === "local"
        ? `local · seeds=${(p.seeds ?? []).join(",")}`
        : `global · communities=${p.communities}`;
    case "answer":
      return `${(p.text ?? "").length} chars · ${p.citations?.length ?? 0} citations · ${p.provider}`;
    case "node_start":
    case "node_end":
      return ev.node ?? "";
    case "error":
      return String(p.message ?? "");
    default: {
      const s = JSON.stringify(p);
      return s === "{}" ? "" : s;
    }
  }
}
