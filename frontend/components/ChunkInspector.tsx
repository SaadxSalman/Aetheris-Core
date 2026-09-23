"use client";
/* Per-chunk retrieval + grading inspector (why a chunk was accepted/rejected). */
import clsx from "clsx";
import { Boxes, CircleCheck, CircleX } from "lucide-react";
import type { GradedChunk } from "@/lib/types";
import { Badge, Card } from "./ui";

export default function ChunkInspector({ chunks }: { chunks: GradedChunk[] }) {
  const sorted = [...chunks].sort(
    (a, b) => (a.rank ?? 999) - (b.rank ?? 999) || (b.rrf_score ?? 0) - (a.rrf_score ?? 0),
  );
  return (
    <Card
      title="Chunk Inspector"
      icon={Boxes}
      actions={
        <span className="font-mono text-[10px] text-slate-500">{chunks.length} chunks</span>
      }
      bodyClassName="p-1.5 space-y-1.5"
    >
      {sorted.length === 0 && (
        <p className="p-4 text-center text-[11px] text-slate-600">
          Retrieved chunks and their grade decisions appear here live.
        </p>
      )}
      {sorted.map((c) => (
        <article
          key={c.chunk_id}
          className={clsx(
            "rounded-lg border p-2 transition",
            c.graded && c.accepted === true
              ? "border-emerald-500/40 bg-emerald-500/[0.06]"
              : c.graded && c.accepted === false
                ? "border-rose-500/40 bg-rose-500/[0.06]"
                : "border-slate-700/50 bg-slate-900/50",
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                {c.rank != null && (
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] font-bold text-slate-400">
                    #{c.rank}
                  </span>
                )}
                <span className="truncate text-[11.5px] font-semibold text-slate-200">
                  {c.title || c.chunk_id}
                </span>
              </div>
              {c.header_path && (
                <div className="mt-0.5 truncate text-[10px] text-slate-500" title={c.header_path}>
                  {c.header_path}
                </div>
              )}
            </div>
            {c.graded ? (
              c.accepted ? (
                <CircleCheck size={14} className="shrink-0 text-emerald-400" />
              ) : (
                <CircleX size={14} className="shrink-0 text-rose-400" />
              )
            ) : (
              <Badge tone="slate">retrieved</Badge>
            )}
          </div>

          <div className="mt-1.5 flex flex-wrap gap-1">
            <Badge tone="cyan">{c.source}</Badge>
            {c.rrf_score != null && <Badge tone="slate">rrf {c.rrf_score.toFixed(4)}</Badge>}
            {c.raw != null && (
              <Badge tone={c.raw >= 0.4 ? "emerald" : c.raw >= 0.18 ? "amber" : "rose"}>
                rel {c.raw.toFixed(2)}
              </Badge>
            )}
            {c.retrievers &&
              Object.entries(c.retrievers).map(([name, rank]) => (
                <Badge key={name} tone="violet">
                  {name}@{rank}
                </Badge>
              ))}
          </div>

          {c.grade_reason && (
            <p
              className={clsx(
                "mt-1.5 font-mono text-[9.5px] leading-snug",
                c.accepted ? "text-emerald-400/90" : "text-rose-400/90",
              )}
            >
              {c.grade_reason}
            </p>
          )}
          {c.snippet && !c.grade_reason && (
            <p className="mt-1.5 line-clamp-2 text-[10.5px] leading-snug text-slate-500">
              {c.snippet}
            </p>
          )}
        </article>
      ))}
    </Card>
  );
}
