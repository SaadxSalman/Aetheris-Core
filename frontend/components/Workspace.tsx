"use client";
/* Workspace composition: chat | live agent canvas | telemetry inspector. */
import clsx from "clsx";
import { Activity, Boxes, DatabaseZap, GitFork } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { useEngine } from "@/hooks/useEngine";
import type { CorpusDoc, EngineConfig, Health, KnowledgeGraph, Stats } from "@/lib/types";
import AgentCanvas from "./AgentCanvas";
import ChatPanel from "./ChatPanel";
import ChunkInspector from "./ChunkInspector";
import CorpusPanel from "./CorpusPanel";
import EventLog from "./EventLog";
import KnowledgeCanvas from "./KnowledgeCanvas";
import TopBar from "./TopBar";
import { Badge } from "./ui";

export default function Workspace() {
  const engine = useEngine();
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<EngineConfig | null>(null);
  const [docs, setDocs] = useState<CorpusDoc[]>([]);
  const [kgraph, setKgraph] = useState<KnowledgeGraph | null>(null);
  const [tab, setTab] = useState<"telemetry" | "chunks" | "corpus">("telemetry");
  const [view, setView] = useState<"agents" | "knowledge">("agents");

  const refresh = useCallback(async () => {
    const [h, s, c, corp, kg] = await Promise.allSettled([
      apiGet<Health>("/api/health"),
      apiGet<Stats>("/api/stats"),
      apiGet<EngineConfig>("/api/config"),
      apiGet<{ documents: CorpusDoc[] }>("/api/corpus"),
      apiGet<KnowledgeGraph>("/api/graph"),
    ]);
    if (h.status === "fulfilled") setHealth(h.value);
    if (s.status === "fulfilled") setStats(s.value);
    if (c.status === "fulfilled") setConfig(c.value);
    if (corp.status === "fulfilled") setDocs(corp.value.documents);
    if (kg.status === "fulfilled") setKgraph(kg.value);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 20000);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!engine.running && engine.lastMs !== null) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine.running]);

  const tabTabs = [
    { id: "telemetry", label: "Telemetry" },
    { id: "chunks", label: `Chunks${engine.chunks.length ? ` · ${engine.chunks.length}` : ""}` },
    { id: "corpus", label: `Corpus · ${docs.length}` },
  ];

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TopBar health={health} stats={stats} config={config} />

      <main className="grid min-h-0 flex-1 grid-cols-[minmax(330px,400px)_1fr_minmax(300px,370px)] gap-3 p-3">
        {/* ── left: query + answer + citations ── */}
        <div className="min-h-0 overflow-y-auto pr-0.5">
          <ChatPanel
            running={engine.running}
            answer={engine.answer}
            citations={engine.citations}
            meta={engine.meta}
            grade={engine.gradeInfo}
            grounding={engine.grounding}
            audit={engine.audit}
            error={engine.error}
            lastMs={engine.lastMs}
            onRun={engine.run}
            onStop={engine.stop}
          />
        </div>

        {/* ── center: live canvases ── */}
        <section className="panel flex min-h-0 flex-col">
          <header className="flex items-center justify-between gap-2 border-b border-slate-700/40 px-3 py-2">
            <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
              <Activity size={13} className="text-cyan-400" />
              {view === "agents" ? "Live Agent Telemetry" : "Entity Knowledge Mesh"}
            </h2>
            <div className="flex items-center gap-1.5">
              {engine.running && (
                <Badge tone="cyan">
                  <span className="blink">● executing</span>
                </Badge>
              )}
              <div className="flex gap-1 rounded-lg bg-slate-900/70 p-1">
                <button
                  onClick={() => setView("agents")}
                  className={clsx(
                    "flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                    view === "agents"
                      ? "bg-slate-700/80 text-cyan-300"
                      : "text-slate-400 hover:text-slate-200",
                  )}
                >
                  <GitFork size={11} /> agent graph
                </button>
                <button
                  onClick={() => setView("knowledge")}
                  className={clsx(
                    "flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                    view === "knowledge"
                      ? "bg-slate-700/80 text-cyan-300"
                      : "text-slate-400 hover:text-slate-200",
                  )}
                >
                  <Boxes size={11} /> knowledge graph
                </button>
              </div>
            </div>
          </header>
          <div className="min-h-0 flex-1">
            {view === "agents" ? (
              <AgentCanvas nodes={engine.nodes} />
            ) : (
              <KnowledgeCanvas data={kgraph} />
            )}
          </div>

          <footer className="flex flex-wrap items-center gap-1.5 border-t border-slate-700/40 px-3 py-1.5">
            {engine.route && <Badge tone="violet">route · {engine.route.route}</Badge>}
            {engine.fusion && (
              <Badge tone="cyan">
                rrf · fused {engine.fusion.fused} (k={engine.fusion.rrf_k})
              </Badge>
            )}
            {engine.sql && <Badge tone="amber">sql · {engine.sql.label}</Badge>}
            {engine.graphCtx?.mode && (
              <Badge tone="emerald">
                graph · {engine.graphCtx.mode}
                {engine.graphCtx.seeds
                  ? ` (${engine.graphCtx.seeds.slice(0, 3).join(", ")})`
                  : ""}
              </Badge>
            )}
            {engine.reforms.map((r) => (
              <Badge key={r.attempt} tone="amber">
                rewrite #{r.attempt} · {r.strategy}
              </Badge>
            ))}
            {!engine.route && !engine.running && (
              <span className="text-[10.5px] text-slate-600">
                Run a query — node badges stream route, fusion, grade and grounding telemetry.
              </span>
            )}
          </footer>

        </section>

        {/* ── right: inspector tabs ── */}
        <section className="panel flex min-h-0 flex-col">
          <header className="flex items-center justify-between gap-2 border-b border-slate-700/40 px-3 py-2">
            <div className="flex gap-1 rounded-lg bg-slate-900/70 p-1">
              {tabTabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id as typeof tab)}
                  className={clsx(
                    "rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                    tab === t.id
                      ? "bg-slate-700/80 text-cyan-300 shadow"
                      : "text-slate-400 hover:text-slate-200",
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <DatabaseZap size={13} className="text-slate-600" />
          </header>
          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === "telemetry" && <EventLog events={engine.events} />}
            {tab === "chunks" && <ChunkInspector chunks={engine.chunks} />}
            {tab === "corpus" && (
              <div className="h-full overflow-y-auto p-2">
                <CorpusPanel docs={docs} onChanged={refresh} />
              </div>
            )}
          </div>
        </section>

      </main>

      <footer className="flex items-center gap-4 border-t border-slate-800/80 bg-slate-950/80 px-4 py-1.5 font-mono text-[10px] text-slate-600">
        <span>reranker · {config?.reranker_provider ?? "auto"}</span>
        <span>crag_threshold · {config?.crag_threshold ?? "—"}</span>
        <span>grounding_threshold · {config?.grounding_threshold ?? "—"}</span>
        <span>top_k · {config?.top_k ?? "—"}</span>
        <span>bm25_docs · {stats?.bm25_docs ?? "—"}</span>
        <span>vectors · {stats?.vector.vectors ?? "—"}</span>
        <span className="ml-auto">
          sse · {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:4000"}
        </span>
      </footer>

    </div>
  );
}
