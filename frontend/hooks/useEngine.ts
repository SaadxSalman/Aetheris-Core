"use client";
/* Live engine state: consumes the orchestrator SSE stream and projects it
   onto node statuses, chunk grades, citations, and telemetry. */
import { useCallback, useRef, useState } from "react";
import { streamQuery } from "@/lib/api";
import type {
  AgentNodeKey,
  AnswerMeta,
  Citation,
  FusionInfo,
  GradeInfo,
  GradedChunk,
  GroundingInfo,
  NodeInfo,
  RouteInfo,
  SqlInfo,
  UiEvent,
} from "@/lib/types";

const initialNodes = (): Record<AgentNodeKey, NodeInfo> => ({
  query: { status: "idle" },
  intent_router: { status: "idle" },
  retrieve: { status: "idle" },
  rerank: { status: "idle" },
  grade: { status: "idle" },
  reformulate: { status: "idle" },
  web_fallback: { status: "idle" },
  verify_grounding: { status: "idle" },
  generate: { status: "idle" },
  answer: { status: "idle" },
});

export function useEngine() {
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<UiEvent[]>([]);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [nodes, setNodes] = useState<Record<AgentNodeKey, NodeInfo>>(initialNodes);
  const [chunks, setChunks] = useState<GradedChunk[]>([]);
  const [route, setRoute] = useState<RouteInfo | null>(null);
  const [gradeInfo, setGradeInfo] = useState<GradeInfo | null>(null);
  const [grounding, setGrounding] = useState<GroundingInfo | null>(null);
  const [fusion, setFusion] = useState<FusionInfo | null>(null);
  const [sql, setSql] = useState<SqlInfo | null>(null);
  const [graphCtx, setGraphCtx] = useState<Record<string, any> | null>(null);
  const [reforms, setReforms] = useState<any[]>([]);
  const [webInfo, setWebInfo] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [meta, setMeta] = useState<AnswerMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastMs, setLastMs] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const patch = useCallback((key: AgentNodeKey, info: Partial<NodeInfo>) => {
    setNodes((prev) => ({ ...prev, [key]: { ...prev[key], ...info } }));
  }, []);

  const mergeChunk = useCallback(
    (piece: Partial<GradedChunk> & { chunk_id: string }) => {
      setChunks((prev) => {
        const idx = prev.findIndex((c) => c.chunk_id === piece.chunk_id);
        if (idx === -1) {
          return [
            ...prev,
            {
              retrieved: false,
              graded: false,
              title: "",
              source: "internal",
              ...piece,
              chunk_id: piece.chunk_id,
            } as GradedChunk,
          ];
        }
        const next = [...prev];
        next[idx] = { ...next[idx], ...piece };
        return next;
      });
    },
    [],
  );

  const reset = useCallback(() => {
    setEvents([]);
    setAnswer("");
    setCitations([]);
    setNodes(initialNodes());
    setChunks([]);
    setRoute(null);
    setGradeInfo(null);
    setGrounding(null);
    setFusion(null);
    setSql(null);
    setGraphCtx(null);
    setReforms([]);
    setWebInfo(null);
    setAudit(null);
    setMeta(null);
    setError(null);
    setLastMs(null);
  }, []);

  const apply = useCallback(
    (ev: UiEvent) => {
      const p = (ev.payload ?? {}) as any;
      if (ev.type !== "answer_delta") {
        setEvents((prev) => [...prev.slice(-399), ev]);
      }
      switch (ev.type) {
        case "run_start":
          setNodes({ ...initialNodes(), query: { status: "running" } });
          break;
        case "node_start":
          if (ev.node) patch(ev.node as AgentNodeKey, { status: "running" });
          break;
        case "node_end":
          if (ev.node)
            patch(ev.node as AgentNodeKey, {
              status: p.status === "error" ? "failed" : "success",
            });
          break;
        case "route_selected":
          patch("intent_router", { badge: String(p.route), detail: p.reasons?.[0] });
          setRoute(p as RouteInfo);
          break;
        case "sql_result":
          patch("retrieve", { badge: `SQL · ${p.rows ?? 0} rows` });
          setSql(p as SqlInfo);
          break;
        case "graph_context":
          setGraphCtx(p);
          break;
        case "retrieval_fusion":
          patch("retrieve", {
            badge: `${p.fused} fused`,
            detail: `bm25 ${p.counts?.bm25 ?? 0} · dense ${p.counts?.dense ?? 0} · graph ${p.counts?.graph ?? 0}`,
          });
          setFusion(p as FusionInfo);
          break;
        case "chunk_retrieved":
          mergeChunk({
            chunk_id: p.chunk_id, rank: p.rank, title: p.title,
            header_path: p.header_path, source: p.source, rrf_score: p.rrf_score,
            snippet: p.snippet, retrievers: p.retrievers,
            retrieved: true, graded: false,
          });
          break;
        case "rerank_complete":
          patch("rerank", { badge: `top ${p.top_k} · ${p.provider}` });
          for (const r of p.results ?? []) {
            mergeChunk({
              chunk_id: r.chunk_id, rank: r.rank, rerank_score: r.score,
              raw: r.raw, title: r.title, source: r.source,
            });
          }
          break;
        case "chunk_graded":
          mergeChunk({
            chunk_id: p.chunk_id, rank: p.rank, accepted: p.accepted,
            grade_reason: p.reason, raw: p.score, rerank_score: p.normalized,
            title: p.title, source: p.source, graded: true,
          });
          break;
        case "grade_result":
          patch("grade", {
            status: p.passed ? "success" : "failed",
            badge: `${Number(p.confidence).toFixed(2)} / ${p.threshold}`,
            detail: p.passed ? "context accepted" : "context rejected → repair",
          });
          setGradeInfo(p as GradeInfo);
          break;
        case "query_reformulated":
          patch("reformulate", {
            badge: `#${p.attempt} ${p.strategy}`,
            detail: String(p.after).slice(0, 60),
          });
          setReforms((prev) => [...prev, p]);
          break;
        case "web_fallback":
          if (!p.skipped) {
            patch("web_fallback", {
              status: p.count > 0 ? "success" : "failed",
              badge: `${p.count ?? 0} results · ${p.provider ?? ""}`,
            });
          }
          setWebInfo(p);
          break;
        case "grounding_check":
          patch("verify_grounding", {
            status: p.passed ? "success" : "failed",
            badge: `${Number(p.score).toFixed(2)} / ${p.threshold}`,
            detail: p.note,
          });
          setGrounding(p as GroundingInfo);
          break;
        case "answer_delta":
          setAnswer((prev) => prev + (p.text ?? ""));
          break;
        case "grounding_audit":
          setAudit(p);
          break;
        case "answer":
          if (typeof p.text === "string" && p.text.length > 0) setAnswer(p.text);
          setCitations(p.citations ?? []);
          setMeta(p as AnswerMeta);
          patch("answer", { status: "success", badge: "delivered" });
          break;
        case "error":
          setError(p.message ?? String(p.stage ?? "error"));
          break;
        case "run_end":
          if (p.status === "error") {
            patch("query", { status: "failed" });
          } else {
            patch("query", { status: "success", badge: `${Math.round(p.elapsed_ms)} ms` });
          }
          setLastMs(p.elapsed_ms ?? null);
          break;
        default:
          break;
      }
    },
    [mergeChunk, patch],
  );

  const run = useCallback(
    async (query: string, mode: string = "auto") => {
      if (!query.trim() || running) return;
      reset();
      setRunning(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        for await (const ev of streamQuery({ query: query.trim(), mode }, ctrl.signal)) {
          apply(ev);
        }
      } catch (e: any) {
        if (e?.name !== "AbortError") setError(e?.message ?? String(e));
      } finally {
        setRunning(false);
        abortRef.current = null;
      }
    },
    [apply, reset, running],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  return {
    running, events, answer, citations, nodes, chunks, route, gradeInfo,
    grounding, fusion, sql, graphCtx, reforms, webInfo, audit, meta, error,
    lastMs, run, stop, reset,
  };
}


