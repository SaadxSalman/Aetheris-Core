# ⬡ Aetheris Core

**Autonomous Multi-Modal Polyglot GraphRAG Engine** — a self-healing, stateful, multi-agent enterprise intelligence mesh that *refuses to hallucinate*.

Instead of the classic linear pipeline *(query → embed → top-k chunk → generate)*, Aetheris Core executes a **conditional LangGraph state machine** that decomposes cross-domain questions, runs **parallel hybrid searches** across a dual-engine store (**BM25 + dense vectors + Personalized PageRank knowledge-graph traversal**), **reranks with a cross-encoder**, **grades its own context (Corrective RAG)**, self-corrects through a query-reformulation loop or a **live web-search fallback**, verifies **grounding** before a single token is streamed, and attaches an **HMAC cryptographic attestation to every citation** — all visualized live on a **React Flow telemetry canvas** over **Server-Sent Events**.

```
   User Query
        │
        ▼
┌────────────────────┐   semantic dispatch   ┌──────────────────────────────────┐
│ Intent Router Agent │ ───────────────────► │ Structured SQL │ Vector │ Graph │ Web │
└────────────────────┘                       └──────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│      Hybrid Retrieval Engine  (BM25 + Dense + PPR Graph)    │  ← weighted RRF fusion
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│ Cross-Encoder Reranker   │  (Flashrank / Cohere / heuristic)
└──────────────────────────┘
        │
        ▼
┌─────────────────────────────┐  fail   ┌──────────────────────────┐
│ Corrective Grader (CRAG)    │ ──────► │ Query Reformulation Loop │──┐
└─────────────────────────────┘         ├──────────────────────────┤  │
        │ pass                          │   Web Fallback Cascade   │  │
        ▼                               └──────────────────────────┘  │
┌─────────────────────────────┐                       ▲───────────────┘
│ Grounding Verification Node │ ── repair (bounded) ──┘
└─────────────────────────────┘
        │ grounded
        ▼
  Final streamed response  +  HMAC-attested citations  +  trace telemetry
```

---

## Table of Contents

1. [Vision — Why Not Linear RAG](#1-vision--why-not-linear-rag)
2. [Architectural Blueprint](#2-architectural-blueprint)
3. [Repository Map](#3-repository-map)
4. [Technology Stack](#4-technology-stack)
5. [How an Answer Is Produced (Walkthrough)](#5-how-an-answer-is-produced-walkthrough)
6. [Core Feature Deep-Dives](#6-core-feature-deep-dives)
7. [Agent Graph Node Reference](#7-agent-graph-node-reference)
8. [SSE Event Catalog](#8-sse-event-catalog)
9. [HTTP API Reference](#9-http-api-reference)
10. [Quickstart](#10-quickstart)
11. [Complete `.env` Configuration Reference](#11-complete-env-configuration-reference)
12. [Activating the Polyglot Backends](#12-activating-the-polyglot-backends)
13. [Zero-Key Fallback Matrix](#13-zero-key-fallback-matrix)
14. [Data Model](#14-data-model)
15. [Ingestion Pipeline](#15-ingestion-pipeline)
16. [Testing & Validation](#16-testing--validation)
17. [Development Guide](#17-development-guide)
18. [Security Model](#18-security-model)
19. [Operations & Troubleshooting](#19-operations--troubleshooting)
20. [Performance & Scaling](#20-performance--scaling)
21. [FAQ](#21-faq)
22. [Roadmap](#22-roadmap)

---

## 1. Vision — Why Not Linear RAG

Classic RAG fails in predictable ways:

| Linear RAG failure mode | Aetheris Core answer |
|---|---|
| Retrieves top-k blindly, then hallucinates when chunks are irrelevant | **CRAG grader** computes a context confidence score; below threshold the engine *refuses* to generate and repairs itself |
| Loses document context after fixed-size splitting | **Contextual Chunk-Header Injector** prepends the parent heading breadcrumb before embedding |
| Only matches surface keywords | **Three-way hybrid retrieval**: BM25 (lexical) + dense embeddings (semantic) + Personalized PageRank (relational), fused with weighted RRF |
| Cannot answer *"what are the broad themes across everything?"* | **Dual-level GraphRAG**: *local search* (entity subgraphs) and *global search* (community summaries) |
| No way to inspect *why* the model said that | **Live SSE telemetry**: route scores, per-chunk accept/reject decisions, grades, streamed to a React Flow canvas |
| Unverifiable sources | **HMAC-SHA256 citation attestations** bound to (chunk id · content digest · request id) |
| Stale internal knowledge | **Web fallback cascade** (Tavily → SerpAPI → DuckDuckGo) merges live results into the same fusion/rerank/grade loop |

The result behaves less like a prompt template and more like an **operations console for retrieval**.

---

## 2. Architectural Blueprint

### 2.1 Three polyglot tiers

```
┌────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js 15 · Tailwind v4 · shadcn-style UI · React Flow       │
│  • Query composer, streamed answer, citation verifier                      │
│  • Live agent-graph canvas (node status + animated edges)                  │
│  • Knowledge-graph canvas, telemetry log, chunk inspector, corpus manager  │
└───────────────────────────────▲────────────────────────────────────────────┘
                                │  HTTP + SSE (POST /api/query)
┌───────────────────────────────┴────────────────────────────────────────────┐
│  GATEWAY — Node.js 26 · Fastify 5 · TypeScript                             │
│  • x-api-key enforcement, per-IP rate limiting, request IDs                │
│  • SSE byte-stream proxy (socket hijack + pipe, zero buffering)            │
│  • JSON proxy: health · config · stats · corpus · graph · ingest · verify  │
└───────────────────────────────▲────────────────────────────────────────────┘
                                │  HTTP + SSE (POST /api/v1/query)
┌───────────────────────────────┴────────────────────────────────────────────┐
│  ORCHESTRATOR — Python 3.14 · LangGraph · FastAPI · httpx                  │
│  • 8-node conditional state machine (CRAG + grounding loops)               │
│  • Ingestion: chunker → header injector → embedder → extractor → graph     │
│  • Dual store: SQLite ⇄ Supabase/pgvector ⇄ local cosine index             │
│               NetworkX ⇄ Neo4j ⇄ local graph JSON                          │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 The LangGraph state machine

```
START ─► intent_router ─┬─(route=web)─► web_fallback ─┐
                        └──────────────► retrieve ◄────┘
                                          │  (bm25 + dense + ppr + communities + sql)
                                          ▼
                                       rerank ─► grade
                                                   │
              ┌────────────────────────────────────┼───────────────────────────────┐
              │ fail (rewrites left)               │ fail (rewrites exhausted)     │ pass
              ▼                                    ▼                               ▼
        reformulate ──► retrieve            web_fallback ──► retrieve      verify_grounding
              ▲                                                            │           │
              └────────────────── repair (bounded) ─────────────────────────┘           │ grounded
                                                                                        ▼
                                                                                   generate ─► END
```

Every loop is **hard-bounded**: `CRAG_MAX_REFORMULATIONS`, `GROUNDING_MAX_REPAIRS`, exactly one web attempt, plus a global `steps > 20` circuit-breaker — the graph can never spin forever, even against adversarial input.

### 2.3 Design principles

1. **Never generate from ungraded context.** The grader sits between reranking and generation, always.
2. **Everything is an event.** Every decision emits a structured SSE event; the UI is a pure projection of that stream.
3. **Graceful polyglot fallback.** Supabase/Neo4j/LLM keys are *activations*, not requirements — the engine is fully functional offline.
4. **Content-addressed truth.** Documents and chunks are identified by content hashes; ingestion is idempotent.
5. **Attribution is cryptographic.** A citation that cannot be HMAC-verified is a bug.

---

## 3. Repository Map

```
Aetheris-Core/
├── .env                        ← MASTER config (ALL keys) — GIT-IGNORED
├── .gitignore                  ← keeps .env, .data, node_modules, .venv, .next out
├── README.md                   ← this file
│
├── orchestrator/               ← Python tier (LangGraph + FastAPI)
│   ├── requirements.txt
│   ├── run.py                  ← uvicorn entrypoint
│   └── aetheris/
│       ├── api.py              ← FastAPI app + SSE endpoint + REST surface
│       ├── config.py           ← root .env loader + public_config()
│       ├── runtime.py          ← process singletons (stores, BM25, embedder)
│       ├── telemetry.py        ← per-request async event bus + NodeTrace
│       ├── llm.py              ← OpenAI-compatible streaming + extractive fallback
│       ├── embeddings.py       ← local hashed embedder + remote embeddings client
│       ├── attribution.py      ← HMAC-SHA256 citation attestations
│       ├── textutils.py        ← tokenizer, stopwords, sentences, synonyms
│       ├── demo_data.py        ← seed corpus (4 documents)
│       ├── graph/
│       │   ├── state.py        ← AgentState TypedDict
│       │   ├── nodes.py        ← all 8 agent nodes
│       │   └── builder.py      ← StateGraph wiring + conditional edges
│       ├── store/
│       │   ├── meta_store.py   ← SQLite source of truth (+ guarded SQL executor)
│       │   ├── vector_store.py ← Supabase pgvector ⇄ local cosine index
│       │   ├── graph_store.py  ← Neo4j ⇄ NetworkX (PPR + communities)
│       │   └── bm25.py         ← pure-Python BM25Okapi
│       ├── ingest/
│       │   ├── chunker.py      ← heading-aware chunker + HEADER INJECTOR
│       │   ├── extractor.py    ← entity/relation extraction (LLM ⇄ heuristic)
│       │   └── pipeline.py     ← end-to-end ingestion + community rebuild
│       └── retrieval/
│           ├── rerank.py       ← Flashrank ⇄ Cohere ⇄ heuristic cross-scorer
│           ├── web.py          ← Tavily ⇄ SerpAPI ⇄ DuckDuckGo
│           └── sql_tool.py     ← natural language → guarded SQL templates
│
├── gateway/                    ← Node.js tier (Fastify 5 + TypeScript)
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── env.ts              ← climbs to repo root, parses the master .env
│       └── index.ts            ← auth, rate limit, JSON proxy, SSE pipe
│
├── frontend/                   ← Next.js 15 tier
│   ├── package.json / tsconfig.json / next.config.ts / postcss.config.mjs
│   ├── app/                    ← layout, page, globals.css (Tailwind v4)
│   ├── lib/                    ← api.ts (SSE client), types.ts
│   ├── hooks/useEngine.ts      ← SSE → UI state reducer
│   └── components/             ← Workspace, AgentCanvas, ChatPanel, EventLog,
│                                  ChunkInspector, CorpusPanel, KnowledgeCanvas,
│                                  TopBar, ui.tsx
│
├── deploy/
│   ├── supabase_setup.sql      ← pgvector table + match RPC + RLS
│   └── neo4j_setup.cypher      ← constraints + optional GDS snippets
│
├── scripts/
│   ├── start-all.ps1           ← boot all 3 tiers (installs/builds if needed)
│   ├── stop-all.ps1            ← kill by port + command line (no orphans)
│   └── smoke_test.py           ← 22-check end-to-end validation suite
│
└── .data/                      ← runtime state (GIT-IGNORED)
    ├── aetheris.db             ← SQLite source of truth
    ├── vectors.json            ← local vector index
    ├── graph.json              ← local knowledge graph
    └── *.log                   ← service logs
```

---

## 4. Technology Stack

| Layer | Technologies | Role in Aetheris Core |
|---|---|---|
| **Orchestration** | Python 3.14, **LangGraph**, FastAPI, uvicorn | Conditional state-machine loops for planning, reflection, CRAG correction, grounding repair |
| **Backend API** | **Node.js 26, Fastify 5, TypeScript** | High-throughput async gateway: API-key auth, rate limiting, request IDs, **SSE fan-out** |
| **Storage & indices** | SQLite, **Supabase (pgvector)**, **Neo4j** / NetworkX | Dual-layer persistence: dense vector similarity **+** explicit entity-relationship knowledge graph |
| **Retrieval & rerank** | BM25 (built-in), **BGE-M3 / Snowflake Arctic Embeddings**, **Flashrank / Cohere** | Hybrid lexical+semantic+graph indexing fused via **weighted Reciprocal Rank Fusion**, cross-encoder reranked |
| **LLM generation** | OpenAI-compatible APIs, Groq, Ollama, extractive fallback | Streaming cited answers; every factual sentence must carry a `[n]` citation marker |
| **Web fallback** | Tavily, SerpAPI, DuckDuckGo (keyless) | Corrective-RAG escape hatch that never fails closed |
| **Frontend UI** | **Next.js 15**, React 19, **Tailwind CSS v4**, shadcn-style components, **React Flow** | Real-time telemetry canvas showing live agent node state (planning → routing → grading) |
| **Transit** | **Server-Sent Events** (POST + streaming reader) | One-way multiplexed stream: node lifecycle, decisions, token deltas, final answer |

---

## 5. How an Answer Is Produced (Walkthrough)

Take the query: *"How does the Corrective Grader Agent use the CRAG loop and web fallback?"*

1. **`run_start`** — the API allocates `request_id=req_…`, builds the initial `AgentState`, opens the SSE bus.
2. **`intent_router`** — scores six routes (`vector`, `graph_local`, `graph_global`, `hybrid`, `sql`, `web`) from keyword cues, relationship cues, recency cues, and **entity hits against the knowledge graph**. Here `"Corrective Grader Agent"` matches graph nodes → `route=graph_local`, plan `{bm25, dense, ppr, graph_local}`. Emits `route_selected` with all scores + human-readable reasons.
3. **`retrieve`** — three retrievers run into one fusion pool:
   * BM25 over header-injected chunk text → top-60
   * dense cosine over `embed(query)` → top-60
   * entity seeds → **Personalized PageRank** → related entities → their evidence chunks
   * fusion via weighted RRF → top-16 candidates, each tagged `retrievers: {bm25@3, dense@1, graph@7}`
   * emits `retrieval_fusion` + per-chunk `chunk_retrieved`
4. **`rerank`** — cross-encoder (Flashrank if installed, Cohere if keyed, else the deterministic heuristic scorer) re-orders candidates and cuts to `RERANK_TOP_K=6`. Emits `rerank_complete`.
5. **`grade`** — the CRAG grader computes
   `confidence = 0.45·mean(top3 raw relevance) + 0.35·query coverage + 0.20·source diversity`
   and emits a `chunk_graded` accept/reject **with a written reason** for every chunk (`raw relevance 0.62 ≥ floor 0.18 — ACCEPTED`), plus one `grade_result`.
6. **Conditional edge** —
   * pass (confidence ≥ `0.42`) → `verify_grounding`
   * fail → `reformulate` (entity-focus → keyword-strip → synonym-expand, or an LLM rewrite on attempt #1) → **retrieve again**
   * still failing after `CRAG_MAX_REFORMULATIONS` → `web_fallback` → results re-enter the same fusion loop as pseudo-chunks
7. **`verify_grounding`** — checks each query aspect (entity seeds, keyword clusters, SQL rows, web evidence) against the accepted context. Fails engage a bounded repair; exhausted repairs set `degraded=true` (the UI flags the answer instead of hiding the problem).
8. **`generate`** — builds numbered `[1..n]` context blocks (chunks + `[SQL]` table + `[GRAPH]` subgraph/community line), streams the answer (LLM deltas or the deterministic extractive composer), and emits `answer_delta` tokens.
9. **Attribution** — each context block becomes a citation record: peppered SHA-256 digest + `HMAC(secret, chunk_id:digest:request_id)`.
10. **`grounding_audit` + `answer` + `run_end`** — a post-hoc audit reports the fraction of answer sentences supported by context; the final `answer` event carries text + citations + grade + degraded flags.

Latency on the seeded corpus: **tens of milliseconds** end-to-end (47 SSE events ≈ 50 ms locally with the extractive fallback).

---

## 6. Core Feature Deep-Dives

### 6.1 Agentic GraphRAG — Dual-Level Retrieval

| Level | Trigger | Algorithm | Context injected |
|---|---|---|---|
| **Local search** | entity-centric questions (`"relationship between X and Y"`, any graph hit) | match seed entities in the query → expand 1-hop neighborhood → **Personalized PageRank** seeded on those nodes (`α=0.85`, 30 iters, edge weight = relation frequency) → evidence chunks linked to top-ranked entities | `[GRAPH]` block: seeds, PPR-ranked related entities, subgraph nodes/edges |
| **Global search** | macro questions (`overall`, `themes`, `landscape`, `trends`, or `mode=global`) | after every ingestion the engine runs **greedy modularity community detection** on the weighted entity graph; each community (≥ `COMMUNITY_MIN_SIZE` members) gets a summary — LLM-written when configured, otherwise an extractive composer over its members' evidence chunks | `[GRAPH]` block: community keywords + community-summary pseudo-chunks entering RRF as first-class candidates |

Community summaries persist in the `communities` table and refresh on every ingest, so global answers stay consistent as the corpus evolves.

### 6.2 Corrective RAG (CRAG) Loop

```
confidence = 0.45 · mean(top-3 raw rerank scores)
           + 0.35 · |query content tokens ∩ context tokens| / |query content tokens|
           + 0.20 · min(1, distinct source docs / 2)

passed  ⟺  confidence ≥ CRAG_CONFIDENCE_THRESHOLD (0.42)
        ∧  ≥1 chunk above the relevance floor (0.18)
```

Repair ladder (each stage bounded, each transition emits telemetry):

1. **Reformulation #1..#N** — strategies in order: `llm_rewrite` (first attempt, when an LLM is configured), `entity_focus` (graph seed names), `keyword_strip` (stopword removal), `synonym_expand` (domain synonym table in `textutils.py`), `fallback_keyword_strip`. Tried variants are recorded so a strategy never repeats.
2. **Web fallback (once)** — Tavily / SerpAPI / DuckDuckGo; results become attributed pseudo-chunks (`web::<i>`) with digests, joining RRF at weight `1.2 × W_DENSE`.
3. **Degraded proceed** — generation is allowed but the response is flagged `degraded=true` (amber badge in the UI) rather than silently pretending.

### 6.3 Contextual Chunk-Header Injector

The single highest-leverage ingestion trick. The chunker tracks the heading stack (Markdown `#`, numbered `1.2`, and `Label:` styles) and prepends a breadcrumb **before embedding**, while storing raw text separately for clean citations.

Input:

```markdown
# Retrieval
...
## Fusion
Reciprocal Rank Fusion combines…
```

Embedded text fed to the vector engine:

```text
[Section: Aetheris Docs > Retrieval > Fusion]
Reciprocal Rank Fusion combines…
```

Effects:
* a 60-word passage inherits its parent topic → dense vectors stop drifting
* BM25 also matches header tokens (weights `W_*` apply to the injected text)
* citations render `header_path` as a breadcrumb, never showing the injection
* every chunk stores `content_sha256 = SHA256(pepper + embedded_text)` → the digest later anchors the HMAC attestation

Chunking parameters: `CHUNK_SIZE=700` chars target, `CHUNK_OVERLAP=140`, sentence-boundary splitting, `CHUNK_HEADER_MAX_LEVELS=4`.

### 6.4 Hybrid Retrieval + Weighted Reciprocal Rank Fusion

Each retriever returns a ranked list; fusion score:

```
score(chunk) = Σ_retriever  W_retriever / (RRF_K + rank_retriever)
W_bm25 = 1.00   W_dense = 1.00   W_graph = 0.85   RRF_K = 60
```

A chunk ranked #1 by both BM25 and dense scores `1/61 + 1/61 ≈ 0.0328`, beating a chunk one retriever placed at #5. Candidates keep per-retriever ranks (`retrievers: {"bm25": 3, "dense": 1, "graph": 7}`) so the UI shows *exactly* which engine surfaced a passage.

### 6.5 Cross-Encoder Rerank Cascade

`RERANKER_PROVIDER=auto` resolves in this order:

1. **Flashrank** — local MS-MARCO cross-encoder if `pip install flashrank` succeeded (no wheel → skipped silently).
2. **Cohere** — `/v1/rerank` when `COHERE_API_KEY` is set (`COHERE_RERANK_MODEL` configurable).
3. **Heuristic cross-scorer** — deterministic two-tower approximation:
   `0.60·recall + 0.25·precision + 0.15·header-alignment + 0.10·adjacent-pair bonus`.
   It emits **absolute** scores in `[0,1]`, which the CRAG floor (`0.18`) compares against.

Scores are min-max normalized across the batch too: `rerank_score` (display) and `rerank_raw` (absolute grading).

### 6.6 Grounding Verification + Post-Hoc Audit

*Pre-generation* (`verify_grounding`): decomposes the active query into aspects — up to 3 graph entity seeds, up to 4 keyword clusters — plus structured-SQL and web-evidence aspects when present. Each aspect must be textually supported by accepted context:

```
score = supported aspects / total aspects   ≥  GROUNDING_MIN_SCORE (0.55)
```

Failures increment `grounding_repairs` (bounded by `GROUNDING_MAX_REPAIRS`) and route back to reformulation; exhaustion sets `degraded`. The node also guarantees **attestability** — any chunk missing a content digest gets one computed on the spot.

*Post-generation* (`grounding_audit`): splits the finished answer into sentences; a sentence counts as supported if it carries a `[n]` citation or ≥ 40% of its content tokens appear in context. The ratio streams as `grounding_audit` and renders as an *"N% supported"* badge.

### 6.7 Cryptographic Source Attribution

```
content_sha256 = SHA-256( CONTENT_HASH_PEPPER ‖ embedded_chunk_text )
attestation     = HMAC-SHA256( ATTRIBUTION_HMAC_SECRET,
                               f"{chunk_id}:{content_sha256}:{request_id}" )
```

* Citation payload shipped to clients: `index, chunk_id, title, header_path, source, uri, snippet, content_sha256, request_id, attestation`.
* Verification recomputes the HMAC with `hmac.compare_digest` (constant-time) **and** checks the stored chunk digest — forgery and corpus tampering both fail.
* The UI exposes a **verify** button per citation; the smoke test asserts valid accept *and* tampered reject.

### 6.8 Intent Router — Route Table

| Route | Signal examples | Retrieval plan |
|---|---|---|
| `sql` | *"how many documents…"*, *"list sources"*, *"stats"* | bm25 + dense + **guarded SQL templates** (+ graph if entities match) |
| `graph_local` | entity names in query, *"relationship between…"*, *"depends on"* | bm25 + dense + **PPR + subgraph context** |
| `graph_global` | *"overall themes"*, *"landscape"*, *"trends"*, `mode=global` | bm25 + dense + **community summaries** |
| `hybrid` | entity hit + topical question (default when graph matches) | all available arms |
| `web` | *"latest"*, *"today"*, *"news"*, *"current"* | bm25 + dense + **immediate web fallback** |
| `vector` | everything else (default) | bm25 + dense |

Route scores are exposed verbatim in `route_selected.scores` and shown as the router node badge.

### 6.9 Structured SQL Dispatch

`sql_tool.py` maps natural language onto **fixed, parameter-free SELECT templates** (never free-form LLM SQL):

| NL pattern | Executed SQL |
|---|---|
| how many documents/files | `SELECT COUNT(*) documents, COUNT(DISTINCT source) sources FROM documents` |
| how many chunks/passages | `SELECT COUNT(*) chunks, SUM(token_count) tokens FROM chunks` |
| list documents/titles | `SELECT title, source, uri FROM documents ORDER BY created_at DESC LIMIT 20` |
| distinct sources | `SELECT source, COUNT(*) documents FROM documents GROUP BY source` |
| top entities | `SELECT name, type, mentions FROM entities ORDER BY mentions DESC LIMIT 12` |
| relationships/edges list | `relationships ⋈ entities` ordered by weight |
| statistics / overview / dashboard | one-row aggregate across all five tables |

Every execution is validated (SELECT-only, single statement, allow-listed tables) and streams as a `sql_result` event with the exact SQL; the markdown table enters generation as a `[SQL]` block.

### 6.10 Web Fallback Cascade

`WEB_SEARCH_PROVIDER=auto` picks **Tavily** (if keyed) → **SerpAPI** (if keyed) → **DuckDuckGo HTML** (keyless). Every result is normalized to `{title, url, snippet}`, converted to an attributed pseudo-chunk (`chunk_id=web::n`, peppered digest, domain breadcrumb), merged into RRF, reranked, and graded like any internal chunk. If all providers fail, `web_fallback` emits `ok:false` with the error and the run continues degraded — the engine never hard-fails on a web outage.

### 6.11 Live Agent Telemetry Visualizer

The React Flow canvas renders ten nodes (`query → intent_router → retrieve ⇄ reformulate / web_fallback → rerank → grade → verify_grounding → generate → answer`) with:

* **live status rings** — idle (dim) → running (cyan pulse) → success (emerald) → failed (rose)
* **badges fed by events** — router shows the chosen route; retrieve shows `16 fused` + per-retriever counts; rerank shows `top 6 · heuristic`; grade shows `0.73 / 0.42` in green/red; reformulate shows `#1 entity_focus`; grounding shows its score; web shows `5 results · duckduckgo`
* **edge choreography** — edges animate only when the transition actually happens: emerald for pass/grounded, amber for fail/repair, violet for re-query loops, cyan for the mainline
* a second canvas (**knowledge graph** view) projecting live entity/typed-edge data with type-colored nodes
* side panels: chronological telemetry log, chunk inspector (accept/reject reasons), corpus manager (ingest + reset), citation verifier

---

## 7. Agent Graph Node Reference

| # | Node | Reads | Writes (state) | Emits | Next |
|---|---|---|---|---|---|
| 1 | `intent_router` | query, mode, graph entity index | `route`, `route_scores`, `route_reasons`, `retrieval_plan` | `route_selected` | `retrieve` (or `web_fallback` when `route=web`) |
| 2 | `web_fallback` | plan, grade, web providers | `web_results`, `web_used`, `web_info`, `degraded` | `web_fallback` | `retrieve` |
| 3 | `retrieve` | plan, active query, BM25, vectors, graph, communities, SQL | `candidates`, `retrieval_counts`, `structured`, `structured_md`, `graph_context` | `retrieval_fusion`, `chunk_retrieved`×12, `graph_context`, `sql_result` | `rerank` |
| 4 | `rerank` | candidates, reranker cascade | `reranked`, `rerank_provider`, `rejected` | `rerank_complete` | `grade` |
| 5 | `grade` | reranked scores, query coverage | `reranked` (+`accepted`, `grade_reason`), `grade` | `chunk_graded`×N, `grade_result` | `verify_grounding` \| `reformulate` \| `web_fallback` |
| 6 | `reformulate` | tried queries, strategies, optional LLM | `active_query`, `tried_queries`, `reformulation_count` | `query_reformulated` | `retrieve` |
| 7 | `verify_grounding` | reranked context, seeds, SQL/web presence | `grounding`, `grounding_repairs`, `degraded` | `grounding_check` | `generate` \| `reformulate` |
| 8 | `generate` | context blocks, LLM / extractive composer | `answer`, `citations` | `answer_delta`×N, `grounding_audit`, `answer` | `END` |

Every node is wrapped in `NodeTrace`, which guarantees a matched `node_start` / `node_end` (with wall-clock `ms`) even when the node throws — the canvas can never show a node stuck in "running".

### State fields (`graph/state.py`)

```
request_id · query · original_query · active_query · tried_queries · mode · steps
route · route_scores · route_reasons · retrieval_plan
candidates · retrieval_counts · structured · structured_md · graph_context
web_results · web_used · web_info
reformulation_count · grounding_repairs · degraded
reranked · rerank_provider · rejected · grade · grounding
citations · answer · error
```

LangGraph merges each node's partial-dict return into this state; conditional edges (`builder.py`) read it to choose the next hop.

---

## 8. SSE Event Catalog

One SSE connection per query run. Frames are `event: <type>` + `data: <json>`; every JSON envelope carries `type, request_id, seq, ts, elapsed_ms[, node, payload]`.

| Event | Key payload fields | Meaning |
|---|---|---|
| `run_start` | `request_id, query, mode` | stream opened, state initialized |
| `node_start` | `node` | agent node began executing |
| `node_end` | `node, status, ms[, error]` | agent node finished |
| `route_selected` | `route, scores{6}, reasons[], plan{}, seeds[]` | intent dispatch decision + why |
| `retrieval_fusion` | `counts{bm25,dense,graph,community,web}, fused, rrf_k, weights` | RRF fusion summary |
| `chunk_retrieved` | `rank, chunk_id, title, header_path, source, rrf_score, retrievers{}, snippet` | per-candidate telemetry (first 12) |
| `graph_context` | `mode: local\|global, seeds[], nodes, edges\|communities` | graph search context injected |
| `sql_result` | `label, sql, columns[], rows, preview[]` | structured dispatch execution |
| `rerank_complete` | `provider, top_k, results[{rank,chunk_id,score,raw,source}]` | cross-encoder output |
| `chunk_graded` | `chunk_id, rank, accepted, score, normalized, reason` | **CRAG per-chunk accept/reject** |
| `grade_result` | `confidence, threshold, passed, coverage, diversity, top_relevance, chunks` | aggregate context grade |
| `query_reformulated` | `attempt, strategy, before, after, remaining` | repair-loop rewrite |
| `web_fallback` | `provider, ok, count, reason, results[{title,url}][, skipped]` | web cascade outcome |
| `grounding_check` | `score, threshold, passed, aspects[{aspect,kind,supported}], repairs, note` | pre-generation grounding |
| `answer_delta` | `text` | streamed token/chunk of the answer |
| `grounding_audit` | `support_ratio, sentences, supported, passed` | post-hoc sentence support ratio |
| `answer` | `text, citations[], provider, degraded, route, confidence, grounding_score, web_used, reformulations, audit` | **final payload** |
| `error` | `stage, message[, action]` | non-fatal/node error (execution continues where possible) |
| `run_end` | `request_id, elapsed_ms, status` | stream closing |

Keep-alive: the server writes `: ping` comment frames every `SSE_HEARTBEAT_SECONDS` (10s) during silence.

Raw consumption example:

```bash
curl -N -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"How does the chunk-header injector work?","mode":"auto"}'
```

---

## 9. HTTP API Reference

### 9.1 Orchestrator (direct, port 8000)

| Method | Path | Body / Params | Returns |
|---|---|---|---|
| `POST` | `/api/v1/query` | `{query, mode?: "auto"\|"local"\|"global", request_id?}` | **SSE stream** (event catalog above) |
| `POST` | `/api/v1/ingest` | `{title, text, source?, uri?, meta?}` | ingest report (chunks, entities, relationships, communities, ms) |
| `GET` | `/api/v1/health` | — | `{status, version, ts}` |
| `GET` | `/api/v1/config` | — | non-secret runtime config (providers, thresholds) |
| `GET` | `/api/v1/stats` | — | meta/vector/graph stats + embedder info |
| `GET` | `/api/v1/corpus` | — | `{documents[], count, stats}` |
| `DELETE` | `/api/v1/corpus` | — | wipes documents/vectors/graph/communities |
| `GET` | `/api/v1/graph` | — | `{nodes[], edges[], communities[], stats}` |
| `GET` | `/api/v1/chunks/{id}` | — | full chunk row (text, header, digest, doc) |
| `POST` | `/api/v1/verify-citation` | `{chunk_id, content_sha256, request_id, attestation}` | `{valid, content_match, expected_content_sha256}` |

Ingest example:

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" -d '{
    "title": "Runbook — Payments",
    "source": "confluence",
    "uri": "https://wiki/payments",
    "text": "# Payments Runbook\n\n## Refunds\nRefunds settle through Stripe within 5 days..."
}'
# → {"doc_id":"doc::…","chunks":3,"entities":7,"relationships":11,"communities":6,"elapsed_ms":41.2}
```

### 9.2 Gateway (port 4000) — same surface, prefixed without `/v1`

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/query` | SSE proxy (socket-hijacked pipe, no buffering) |
| `POST` | `/api/ingest` | JSON proxy |
| `GET` | `/api/health` | includes gateway + orchestrator reachability |
| `GET` | `/api/config` `/api/stats` `/api/corpus` `/api/graph` | JSON proxies |
| `GET` | `/api/chunks/:id` | JSON proxy |
| `DELETE` | `/api/corpus` | JSON proxy |
| `POST` | `/api/verify-citation` | JSON proxy |

Gateway behaviors:
* **Auth** — when `GATEWAY_REQUIRE_AUTH=true`, every route except `/api/health` requires header `x-api-key: $GATEWAY_API_KEY` (401 otherwise). The frontend sends it automatically via `NEXT_PUBLIC_GATEWAY_API_KEY`.
* **Rate limit** — `GATEWAY_RATE_LIMIT_PER_MIN` per client IP (429 beyond).
* **Request IDs** — each request gets `x-request-id` (inbound honored, else generated UUID) and forwards it to the orchestrator for end-to-end trace correlation.
* **Errors** — orchestrator outages return `502 {error:"orchestrator_unreachable", hint:"…"}` instead of hanging.

---

## 10. Quickstart

### Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.11+ (built on 3.14) | orchestrator |
| Node.js | 20+ (built on 26) | gateway + frontend |
| npm | 10+ | packages |
| PowerShell | 5.1+/pwsh | helper scripts (macOS/Linux: run the three commands manually) |

**Zero external accounts required** — the default `.env` runs everything locally with fallback providers.

### Option A — one command

```powershell
.\scripts\start-all.ps1     # creates venv, installs, builds, boots all 3 tiers
# → open http://localhost:3000
```

### Option B — three terminals

```powershell
# 1) orchestrator
cd orchestrator
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt     # or: python -m pip ...
.\.venv\Scripts\python run.py                       # http://127.0.0.1:8000

# 2) gateway
cd gateway
npm install && npm run build
npm start                                           # http://127.0.0.1:4000

# 3) frontend
cd frontend
npm install && npm run build
npm start                                           # http://localhost:3000
```

### Option C — Docker-style minimal check (no UI)

Only the orchestrator is needed for API use: start it, then `python scripts/smoke_test.py`.

### Verify

```powershell
python scripts/smoke_test.py
# … SMOKE TEST: 22/22 checks passed
```

### Demo queries to try

| Query | What you should see |
|---|---|
| *"How does the Corrective Grader Agent use the CRAG loop?"* | `route=graph_local`, PPR seeds, 6 citations |
| *"How many documents and chunks are in the corpus?"* | `route=sql` + `sql_result` table |
| *"overall themes across the platform knowledge mesh"* (+mode **global**) | `route=graph_global`, community pseudo-chunks |
| *"latest news about transformer inference"* (+ web recency words) | `route=web` → web fallback node lights up |
| *"zzzz unrelated gibberish query"* | grader **fails** → reformulation events → possibly web → degraded answer with amber badges |

That last one is the money shot: watch the grade node turn rose, the repair edge animate, and the engine refuse to pretend.

### Shutdown

```powershell
.\scripts\stop-all.ps1       # kills by port + command line (no orphan workers)
```

---

## 11. Complete `.env` Configuration Reference

> ⚠️ **All configuration lives in one master file at the repository root: `.env`.**
> It is listed in `.gitignore` and is **never committed** — there is deliberately **no `.env.example`**; this section *is* the documentation for every key. Each tier reads the same file: the orchestrator via `python-dotenv`, the gateway by walking up from `cwd`, the frontend via `next.config.ts` (only the three `NEXT_PUBLIC_*` values are inlined into the browser bundle).

### 11.1 Application / runtime

| Key | Default | Description |
|---|---|---|
| `APP_NAME` | `Aetheris Core` | display name (health/config responses) |
| `APP_ENV` | `development` | environment label |
| `APP_DEBUG` | `true` | enables uvicorn auto-reload |
| `APP_LOG_LEVEL` | `INFO` | Fastify/uvicorn log level |
| `DATA_DIR` | `.data` | runtime state dir (relative → repo root); holds `aetheris.db`, `vectors.json`, `graph.json`, logs |

### 11.2 Network / ports

| Key | Default | Description |
|---|---|---|
| `ORCHESTRATOR_HOST` / `ORCHESTRATOR_PORT` | `127.0.0.1` / `8000` | FastAPI bind |
| `GATEWAY_HOST` / `GATEWAY_PORT` | `127.0.0.1` / `4000` | Fastify bind |
| `FRONTEND_PORT` | `3000` | Next.js port (`npm start` uses package scripts; keep in sync) |
| `ORCHESTRATOR_URL` | `http://127.0.0.1:8000` | gateway → orchestrator target |
| `PUBLIC_API_BASE_URL` | `http://localhost:4000` | browser → gateway base URL |
| `CORS_ORIGINS` | `http://localhost:3000,...` | comma-separated allowed origins |

### 11.3 Security / keys

| Key | Default | Description |
|---|---|---|
| `GATEWAY_API_KEY` | dev value | shared secret sent as `x-api-key` |
| `GATEWAY_REQUIRE_AUTH` | `false` | `true` enforces the key on every gateway route |
| `ATTRIBUTION_HMAC_SECRET` | dev value | **HMAC key for citation attestations** — change in production |
| `CONTENT_HASH_PEPPER` | dev value | pepper for chunk/document SHA-256 digests |
| `GATEWAY_RATE_LIMIT_PER_MIN` | `120` | per-IP requests/minute |

### 11.4 LLM (answer generation)

| Key | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `none` | `openai` \| `groq` \| `ollama` \| `none` (extractive fallback) |
| `OPENAI_API_KEY` | *(empty)* | key for OpenAI-compatible endpoints |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | swap for Azure/LM Studio/DeepSeek/Together/xAI/Groq-compatible bases |
| `LLM_MODEL` | `gpt-4o-mini` | chat model id |
| `GROQ_API_KEY` / `GROQ_BASE_URL` | *(empty)* / Groq | Groq fast-path |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434/v1` | local Ollama |
| `LLM_TEMPERATURE` | `0.2` | generation temperature |
| `LLM_MAX_TOKENS` | `1400` | max completion tokens |
| `LLM_TIMEOUT_SECONDS` | `90` | request timeout |
| `LLM_MAX_RETRIES` | `2` | retry budget |

### 11.5 Embeddings (dense retrieval)

| Key | Default | Description |
|---|---|---|
| `EMBEDDER_PROVIDER` | `local` | `local` (deterministic hashed embedder, offline) \| `openai_compatible` |
| `EMBEDDING_BASE_URL` | OpenAI | any `/embeddings` endpoint (HF TEI, Jina, OpenAI, local TEI…) |
| `EMBEDDING_API_KEY` | *(empty)* | Bearer key if required |
| `EMBEDDING_MODEL` | `snowflake/snowflake-arctic-embed-l-v2.0` | model id (BGE-M3, Arctic, text-embedding-3…) |
| `EMBEDDING_DIM` | `384` | dimension — **must match the Supabase column when using pgvector** |
| `EMBEDDING_AUTO_DIM` | `true` | detect dimension from the first embeddings response |

Query-side automatically prefixes instruction-style models (bge/arctic/gte/jina/e5) with *"Represent this sentence for searching relevant passages: "*.

### 11.6 Vector backend (Supabase pgvector)

| Key | Default | Description |
|---|---|---|
| `VECTOR_BACKEND` | `auto` | `auto` \| `supabase` \| `local` — `auto` picks Supabase only when URL **and** key are present, and probes connectivity, silently falling back to local |
| `SUPABASE_URL` | *(empty)* | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | *(empty)* | server-side key (preferred) |
| `SUPABASE_ANON_KEY` | *(empty)* | fallback key |
| `SUPABASE_SCHEMA` | `public` | PostgREST schema profile |
| `SUPABASE_VECTOR_TABLE` | `aetheris_chunks` | vector table name |
| `SUPABASE_MATCH_RPC` | `match_aetheris_chunks` | similarity RPC (see `deploy/supabase_setup.sql`) |

### 11.7 Knowledge graph backend (Neo4j)

| Key | Default | Description |
|---|---|---|
| `GRAPH_BACKEND` | `auto` | `auto` picks Neo4j when a password is set + connection probes OK, else NetworkX |
| `NEO4J_URI` | `bolt://localhost:7687` | bolt/neo4j/https URI |
| `NEO4J_USERNAME` | `neo4j` | user |
| `NEO4J_PASSWORD` | *(empty)* | **presence of this value activates Neo4j in `auto` mode** |
| `NEO4J_DATABASE` | `neo4j` | database name (EnterPrise multi-db) |

### 11.8 Retrieval / fusion

| Key | Default | Description |
|---|---|---|
| `RETRIEVAL_TOP_K` | `8` | chunks kept after rerank inputs are cut (`×2` candidates enter rerank) |
| `RETRIEVAL_CANDIDATE_POOL` | `60` | per-retriever pool before fusion |
| `RRF_K` | `60` | Reciprocal Rank Fusion constant |
| `W_BM25` / `W_DENSE` / `W_GRAPH` | `1.0 / 1.0 / 0.85` | per-retriever fusion weights |
| `PPR_ITERATIONS` | `30` | Personalized PageRank iterations |
| `PPR_DAMPING` | `0.85` | PageRank damping factor |
| `PPR_TOP_ENTITIES` | `6` | PPR-ranked entities used for graph chunks |
| `COMMUNITY_MIN_SIZE` | `3` | smallest community kept for global search |
| `COMMUNITY_MAX_LEVELS` | `2` | reserved for hierarchical communities |

### 11.9 Reranker

| Key | Default | Description |
|---|---|---|
| `RERANKER_PROVIDER` | `auto` | `auto` \| `flashrank` \| `cohere` \| `heuristic` |
| `COHERE_API_KEY` | *(empty)* | enables Cohere rerank |
| `COHERE_RERANK_MODEL` | `rerank-english-v3.0` | Cohere model id |
| `RERANK_TOP_K` | `6` | chunks passed to the grader/generator |

Flashrank activation: `pip install flashrank` inside the venv (optional — no wheel ⇒ heuristic).

### 11.10 Corrective RAG (CRAG)

| Key | Default | Description |
|---|---|---|
| `CRAG_CONFIDENCE_THRESHOLD` | `0.42` | context confidence gate — below it the engine repairs instead of generating |
| `CRAG_MAX_REFORMULATIONS` | `2` | maximum query rewrites before the web cascade |
| `CRAG_ENABLE_WEB_FALLBACK` | `true` | allow the web escape hatch |
| `GROUNDING_MIN_SCORE` | `0.55` | minimum supported-aspect ratio (also the audit pass line) |
| `GROUNDING_MAX_REPAIRS` | `1` | grounding repair loops before degraded proceed |

### 11.11 Web search fallback

| Key | Default | Description |
|---|---|---|
| `WEB_SEARCH_PROVIDER` | `auto` | `auto` \| `tavily` \| `serpapi` \| `duckduckgo` |
| `TAVILY_API_KEY` | *(empty)* | https://tavily.com |
| `SERPAPI_API_KEY` | *(empty)* | https://serpapi.com |
| `WEB_RESULT_COUNT` | `5` | results per fallback |
| `WEB_TIMEOUT_SECONDS` | `12` | per-provider timeout |

### 11.12 Ingestion / chunking

| Key | Default | Description |
|---|---|---|
| `CHUNK_SIZE` | `700` | target chunk length (chars), split on sentence boundaries |
| `CHUNK_OVERLAP` | `140` | overlap between adjacent chunks |
| `CHUNK_HEADER_MAX_LEVELS` | `4` | max breadcrumb depth injected before embedding |
| `SEED_DEMO_CORPUS` | `true` | auto-ingest the 4-document demo corpus on first boot (also repairs partial seeds) |

### 11.13 Telemetry / SSE

| Key | Default | Description |
|---|---|---|
| `SSE_HEARTBEAT_SECONDS` | `10` | `: ping` keep-alive cadence |
| `TELEMETRY_MAX_EVENTS` | `600` | per-request event buffer |
| `TELEMETRY_INCLUDE_CHUNKS` | `true` | emit per-chunk `chunk_retrieved` events |

### 11.14 Frontend (inlined at build time)

| Key | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:4000` | browser → gateway |
| `NEXT_PUBLIC_GATEWAY_API_KEY` | dev value | sent as `x-api-key` (only meaningful when auth enforced) |
| `NEXT_PUBLIC_APP_NAME` | `Aetheris Core` | UI label |

> **Production hardening checklist:** regenerate `GATEWAY_API_KEY`, `ATTRIBUTION_HMAC_SECRET`, `CONTENT_HASH_PEPPER`; set `GATEWAY_REQUIRE_AUTH=true`; set `APP_DEBUG=false`; put the gateway behind TLS; restrict `CORS_ORIGINS`.

---

## 12. Activating the Polyglot Backends

### 12.1 Supabase (pgvector)

1. Create a Supabase project → open **SQL Editor** → run `deploy/supabase_setup.sql`.
2. If your embedding dimension ≠ 384, edit `vector(384)` and the RPC parameter type to `EMBEDDING_DIM`.
3. Set in `.env`:
   ```ini
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   EMBEDDER_PROVIDER=openai_compatible      # real embeddings against pgvector
   EMBEDDING_DIM=1024                       # match your model + SQL column
   VECTOR_BACKEND=auto                      # or force "supabase"
   ```
4. Restart the orchestrator — `GET /api/v1/stats` → `"vector":{"backend":"supabase"}`.
5. Any failure (bad key, missing RPC, wrong dimension) probes at startup and **falls back to the local index** instead of crashing.

### 12.2 Neo4j

1. Run a database: `docker run -d --name neo4j -p7474:7474 -p7687:7687 -e NEO4J_AUTH=neo4j/changeit neo4j:5`.
2. Execute `deploy/neo4j_setup.cypher` in the browser (`http://localhost:7474`).
3. Set in `.env`:
   ```ini
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORD=changeit
   GRAPH_BACKEND=auto
   ```
4. Restart → `"graph":{"backend":"neo4j"}` in stats. Writes flow through `sync_document` (MERGE Entity/RELATED/MENTIONS_IN); reads use seed matching, neighbor-PPR approximation (GDS-free), and subgraph expansion.
   Without GDS installed, community detection for global search falls back to grouping — install the GDS plugin for production-grade communities (snippets provided in the cypher file).

### 12.3 LLM providers

```ini
# OpenAI (or any OpenAI-compatible gateway)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Groq
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile

# Fully local via Ollama
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=llama3.2
```

Effects when enabled: streaming `answer_delta` tokens from the model, LLM-based query rewrite on reformulation #1, LLM entity/relation extraction at ingest, LLM community summaries, strict citation-format system prompt.
Effects when `none`: deterministic extractive generator (still fully cited + audited) and heuristic extraction — every smoke test still passes.

### 12.4 Real embeddings (BGE-M3 / Snowflake Arctic)

```ini
EMBEDDER_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=http://localhost:8010/v1     # e.g. HuggingFace TEI
EMBEDDING_API_KEY=                              # if required
EMBEDDING_MODEL=BAAI/bge-m3                     # or snowflake/snowflake-arctic-embed-l-v2.0
EMBEDDING_DIM=1024
```

Any endpoint implementing `POST /embeddings` works (OpenAI, TEI, Jina, Cohere-compat, vLLM, Ollama embeddings). API failures degrade to the local hashed embedder rather than failing ingestion.

### 12.5 Rerankers & web search

```ini
RERANKER_PROVIDER=cohere   # + COHERE_API_KEY=...
# or: pip install flashrank   then RERANKER_PROVIDER=auto

WEB_SEARCH_PROVIDER=tavily # + TAVILY_API_KEY=...
# or leave auto with no keys → DuckDuckGo HTML (keyless)
```

---

## 13. Zero-Key Fallback Matrix

| Capability | With all keys empty (default) | Activated |
|---|---|---|
| Orchestration graph (8 nodes, CRAG + grounding loops) | ✅ LangGraph | — |
| Lexical retrieval | ✅ built-in BM25 | — |
| Dense retrieval | ✅ deterministic hashed embedder (384-d) | `EMBEDDER_PROVIDER=openai_compatible` → BGE-M3/Arctic |
| Vector persistence | ✅ local cosine index (`vectors.json`) | Supabase creds → pgvector |
| Knowledge graph + PPR | ✅ NetworkX + greedy modularity | Neo4j creds → Neo4j |
| Community summaries | ✅ extractive composer | LLM → model-written summaries |
| Reranking | ✅ heuristic cross-scorer (absolute scores) | Flashrank wheel / Cohere key |
| Entity/relation extraction | ✅ typed-pattern heuristics | LLM → JSON extraction |
| Query reformulation | ✅ 3 deterministic strategies | LLM → `llm_rewrite` on attempt #1 |
| Answer generation | ✅ extractive composer, fully cited + audited | `LLM_PROVIDER` → streaming LLM |
| Web fallback | ✅ DuckDuckGo HTML (keyless) | Tavily/SerpAPI keys |
| Structured SQL | ✅ guarded templates over SQLite | — |
| Citation attestation | ✅ HMAC-SHA256 | — |
| Gateway + UI + telemetry | ✅ fully | — |

**Nothing in this repository requires an external account to run end-to-end.**

---

## 14. Data Model

### 14.1 SQLite (source of truth) — `.data/aetheris.db`

```
documents(id, title, source, uri, sha256, created_at, meta_json)
chunks(id, doc_id →documents, ordinal, header_path, text, embedded_text,
       token_count, content_sha256, created_at)
entities(id, name, normalized UNIQUE, type, mentions, doc_id)
relationships(id, src →entities, dst →entities, type, weight, evidence_chunk, doc_id)
entity_chunks(entity_id →entities, chunk_id →chunks)     -- many-to-many mention index
communities(id, level, members_json, size, summary, keywords_json, created_at)
```

IDs are content-addressed: `doc::<sha12>`, `chk::<doc>::<ordinal>::<hash8>`, `ent::<normalized>`, `rel::<src>::<dst>::<type>` — re-ingesting identical content is a no-op update.

### 14.2 Vector layer

| Backend | Storage | Search |
|---|---|---|
| local | `vectors.json` — `{vectors:{chunk_id:[f32…]}, meta:{…}}`, written through on every batch | in-process cosine, deterministic ordering |
| Supabase | table `aetheris_chunks(chunk_id PK, doc_id, header_path, text, embedding vector(n))` | RPC `match_aetheris_chunks(query_embedding, match_count)` → `{chunk_id,…,similarity}` |

### 14.3 Graph layer

Nodes: `Entity {normalized, name, type∈{component,datastore,model,process,artifact,actor,concept}, mentions}`.
Edges: `RELATED {type∈{uses, depends_on, integrates_with, stores, routes, causes, produces, improves, mitigates, related_to}, weight}` plus `MENTIONS_IN → Chunk`.

| Backend | Storage |
|---|---|
| local | `graph.json` — node-link JSON + entity→chunks map + chunk texts (for summary extraction) |
| Neo4j | native `(:Entity)-[:RELATED]->(:Entity)` + `(:Entity)-[:MENTIONS_IN]->(:Chunk)` |

### 14.4 Relationship typing heuristics (offline mode)

Sentence patterns like `(A) causes|uses|depends on|integrates with|stores|routes|improves|mitigates|produces (B)` produce typed edges; remaining same-sentence co-occurrences add `related_to` at weight `0.5`. With an LLM configured, extraction switches to a strict-JSON prompt (30 entities / 40 relations max) while keeping the same storage contract.

---

## 15. Ingestion Pipeline

`POST /api/v1/ingest` → `ingest_document()` executes eight stages:

1. **Normalize + hash** — `sha256(title ‖ text)` ⇒ idempotent `doc::` id; previous chunk ids captured for vector cleanup.
2. **Chunk** — heading stack tracking (Markdown / numbered / `Label:`), sentence-boundary splitting with overlap → `Chunk` objects with `header_path`.
3. **Header injection** — `embedded_text = "[Section: a > b > c]" + text`, digest computed over it.
4. **Persist truth** — document + chunk rows into SQLite (replacing the doc's previous chunks).
5. **Embed + upsert vectors** — old vectors deleted, new batch embedded (remote with local degradation), upserted to the active vector backend.
6. **Extract** — entities/relations (LLM or heuristics) → `entities`, `relationships`, `entity_chunks` tables.
7. **Graph sync** — merge nodes/edges into NetworkX or Neo4j; PPR caches invalidated.
8. **Communities** — greedy modularity decomposition → summaries (LLM or extractive) → `communities` table; BM25 index rebuilt.

The in-process `Runtime` singleton owns all of these stores; the FastAPI lifespan seeds `DEMO_DOCUMENTS` (4 docs / 28 chunks / ~109 entities / 6 communities) when the corpus is empty or when a partial seed is detected (vectors missing while chunks exist).

---

## 16. Testing & Validation

### 16.1 The smoke suite

```powershell
cd orchestrator
.\.venv\Scripts\python.exe ..\scripts\smoke_test.py
# optional: --orchestrator http://127.0.0.1:8000
```

| # | Check | Asserts |
|---|---|---|
| 1 | health | `/api/v1/health` responds `status=ok` |
| 2 | corpus seeded | documents/chunks/entities/relations/communities present |
| 3 | SSE completes | stream ends with `run_end` |
| 4–11 | event contract | all 8 core event types present in order |
| 12 | route | a route is selected and non-empty |
| 13 | grade | `confidence`, `threshold`, `passed` computed |
| 14 | answer | non-empty text |
| 15 | citations | ≥1 citation with digest + attestation |
| 16 | attestation valid | `verify-citation` → `valid:true` |
| 17 | tamper rejected | altered digest → `valid:false` |
| 18–20 | SQL route | `route=sql` + `sql_result` + answer |
| 21–22 | global route | `route=graph_global` + `mode=global` context |

Exit code `0` = all green (CI-friendly).

### 16.2 Build validation

```powershell
cd gateway  && npm run build        # tsc strict, exit 0
cd frontend && npx tsc --noEmit && npm run build   # next build, exit 0
cd orchestrator && python -m compileall aetheris   # exit 0
```

### 16.3 Manual telemetry test

Open `http://localhost:3000`, run the gibberish query, and confirm visually: router picks a route → retrieve fuses → grade **fails** (rose) → reformulate badge increments → possibly web → grounding → degraded/amber answer, with the telemetry log mirroring every transition.

---

## 17. Development Guide

### 17.1 Hot reload

* Orchestrator: `APP_DEBUG=true` runs uvicorn with `--reload` (watches `orchestrator/`).
* Gateway dev: `cd gateway && npm run dev` (tsx watch).
* Frontend dev: `cd frontend && npm run dev` (Next dev on :3000).

### 17.2 Adding a new agent node

1. Implement `async def my_node(state: AgentState, config: RunnableConfig) -> dict` in `orchestrator/aetheris/graph/nodes.py` — wrap the body in `async with NodeTrace(_session(config), "my_node"):` and emit domain events with `await sess.emit(...)`.
2. Add any new state fields to `graph/state.py` (and to `initial_state`).
3. Register it in `graph/builder.py`: `g.add_node("my_node", my_node)` plus edges / a conditional router function.
4. Map its events in `frontend/hooks/useEngine.ts` (`case "my_event": … patch("my_node", …)`).
5. Give it a node on the canvas: add a `LAYOUT` entry + `EDGE_DEFS` in `components/AgentCanvas.tsx`.

The telemetry UI requires zero backend changes beyond emitting well-formed events.

### 17.3 Adding a new retriever

1. Produce a ranked `[(chunk_id, score), …]` list in `retrieve()`.
2. Feed each entry through `_rrf_add(scores, ranks, chunk_id, rank, W_YOUR, "your_retriever")`.
3. Add a weight key to `.env` + `Settings`, and include it in the `retrieval_fusion` payload.
4. Candidates must be either `extra[chunk_id]` records (non-SQLite sources) or valid `chunks` rows.

### 17.4 Adding a route

Extend the score table in `intent_router()` (add the key to `scores`, its cues, and the `plan` arm), then handle the arm in `retrieve()`. Route priority ties are broken by `ROUTE_PRIORITY`.

### 17.5 Frontend conventions

* `hooks/useEngine.ts` is the **only** place that consumes SSE; components are pure projections.
* Components use the shared primitives in `components/ui.tsx` (`Card`, `Badge`, `Button`, `StatusDot`) — Tailwind v4 utility classes, dark slate/cyan/violet palette.
* Type contracts live in `lib/types.ts` and mirror the orchestrator payloads 1:1.

---

## 18. Security Model

| Concern | Control |
|---|---|
| Secret leakage to git | `.env` + `.env.*` ignored (only `.env.example` would be allowed — deliberately absent); `.data/`, `node_modules`, `.venv`, `.next` ignored too |
| API abuse | optional `x-api-key` enforcement (`GATEWAY_REQUIRE_AUTH`), per-IP rate limit, request-size cap (6 MB) |
| SQL injection | structured route uses **fixed templates**; `execute_readonly` re-validates SELECT-only, single statement, allow-listed tables even for future LLM-SQL |
| Citation forgery | HMAC-SHA256 over (chunk, digest, request) verified with `compare_digest`; digest itself is peppered |
| Corpus tampering | verification also compares the recomputed stored digest (`content_match`) |
| Prompt injection from corpus | system prompt confines answers to numbered CONTEXT blocks and mandates "Not found in the internal knowledge mesh" otherwise; grounding + audit provide backpressure |
| Cross-origin | explicit `CORS_ORIGINS` allow-list |
| Browser secrets | only `NEXT_PUBLIC_*` values reach the client; all provider keys stay server-side |

**Note:** `NEXT_PUBLIC_GATEWAY_API_KEY` is by nature visible to browsers — treat it as a *public* client id, keep real protection at the network layer (auth + TLS + rate limits).

---

## 19. Operations & Troubleshooting

### Ports & logs

| Service | Port | Log |
|---|---|---|
| orchestrator | 8000 | `.data/orch.err.log` |
| gateway | 4000 | `.data/gw.err.log` |
| frontend | 3000 | `.data/web.err.log` |

### Common issues

| Symptom | Cause | Fix |
|---|---|---|
| Gateway returns `orchestrator_unreachable` | Python tier not running | `python run.py` in `orchestrator/` (or `start-all.ps1`) |
| Frontend shows "gateway down" | gateway not running | `npm start` in `gateway/` (after `npm run build`) |
| Answers identical for every query | BM25/vectors stale after manual DB edit | restart orchestrator (lifespan rebuilds BM25; seeds if vectors missing) |
| Old server keeps answering / port 8000 busy | orphaned uvicorn reloader child holding the inherited socket | `.\scripts\stop-all.ps1` (kills by port **and** command line), then restart |
| `stats` shows `vectors: 0` with chunks present | partial ingestion (crash mid-seed) | restart — lifespan self-heals when `vectors == 0 && chunks > 0`; or `DELETE /api/corpus` and restart |
| pgvector dimension errors | `EMBEDDING_DIM` ≠ SQL column | edit `deploy/supabase_setup.sql` + `.env`, re-run SQL |
| Neo4j probe fails at boot | wrong creds/network | engine silently falls back to local NetworkX; check `.env` |
| `route=web` but no results | DuckDuckGo unreachable / provider blocked | set `TAVILY_API_KEY`; run still completes (degraded) |
| Cohere/Flashrank not used | key missing / no wheel | check `rerank_complete.provider` event in the telemetry log |
| Smoke test connection refused | orchestrator booting (seeding takes a few seconds) | wait for `Application startup complete` in `orch.err.log` |

### Reset everything

```powershell
.\scripts\stop-all.ps1
Remove-Item -Recurse -Force .data     # nukes db + vectors + graph + logs
.\scripts\start-all.ps1               # re-seeds demo corpus from scratch
```

---

## 20. Performance & Scaling

**Measured on the seeded demo corpus (local fallback providers):**

| Stage | Typical latency |
|---|---|
| BM25 + dense + PPR retrieval + RRF | < 5 ms |
| Heuristic rerank of 16 candidates | < 2 ms |
| Grader + grounding | < 2 ms |
| Full run (47 SSE events, extractive answer) | **~50 ms** |
| Ingest 1 document (~1.5 KB, 7 chunks) | ~40 ms (heuristic extraction) |

Scaling levers, in order of impact:

1. **Vectors → Supabase/pgvector** with an ANN index (ivfflat/hnsw) once you pass ~50k chunks; keeps cold query latency flat.
2. **Graph → Neo4j** for >100k relationships and multi-hop traversals; add GDS for true PageRank + label-propagation communities.
3. **Real embeddings** (BGE-M3/Arctic) — quality jumps far more than latency; embedding happens at ingest, query embedding is one API call.
4. **Flashrank/Cohere rerank** — the heuristic is O(query×chunk) and cheap, but a real cross-encoder materially improves grade stability on noisy corpora.
5. **Tune pools**: `RETRIEVAL_CANDIDATE_POOL` (60) and `RETRIEVAL_TOP_K` (8) dominate retrieval cost; lower them for chat-scale latency budgets.
6. **LLM streaming** — tokens begin flowing as soon as grounding passes; `LLM_MAX_TOKENS` caps tail latency.
7. Horizontal: the orchestrator is stateless per request (state flows through `AgentState` + SSE bus) — run N replicas behind the gateway; sticky sessions unnecessary.

SQLite WAL handles the demo and small-team workloads comfortably; for heavy concurrent ingest, move the meta layer to Postgres (same schema translates directly).

---

## 21. FAQ

**Q: Why is there no `.env.example`?**
Because the requirement is a single master `.env` holding *all* keys, git-ignored, with complete documentation living here in §11 instead of a committable template that could tempt secrets into the repo.

**Q: Does anything phone home with empty keys?**
No. With defaults, every provider resolution stays local (SQLite/local vectors/NetworkX/heuristic rerank/extractive generation). The only outbound call would be the keyless DuckDuckGo fallback — and only when the CRAG cascade actually reaches it.

**Q: Why both SQLite *and* a vector DB?**
SQLite is the auditable source of truth (text, digests, entities, communities, SQL route); vector/graph engines are derived acceleration layers that can be rebuilt from it at any time.

**Q: Is the extractive fallback a real answer?**
It's a grounded, cited, audited extractive summary — ideal when you must run air-gapped. Configure any OpenAI-compatible LLM to get fluent synthesis with the same citation contract.

**Q: How do local vs global GraphRAG differ at query time?**
Local = entity seeds → PPR → subgraph + evidence chunks (specific, relational). Global = community detection → community summaries injected as macro context (thematic). `mode` in the request body forces either; `auto` lets the router decide.

**Q: Can the loops run away?**
No: reformulations ≤ `CRAG_MAX_REFORMULATIONS`, grounding repairs ≤ `GROUNDING_MAX_REPAIRS`, web cascade executes once, and a global `steps > 20` breaker forces generation.

**Q: How is this different from LangChain's standard RAG templates?**
State carries across iterations (reformulated queries, web results, counters), every branch emits telemetry, citations are cryptographically attested, retrieval is three-way + RRF + cross-encoder, and grading/grounding are two *separate* bounded gates.

---

## 22. Roadmap

* [ ] **Weaviate Cloud** vector backend alongside Supabase (interface already abstracted).
* [ ] Hierarchical (multi-level) community summaries for global search.
* [ ] Async ingestion queue + WebSocket ingest progress channel.
* [ ] Evaluation harness: golden-question set with recall/grounding scoreboards over time.
* [ ] Multi-tenant corpora with per-namespace HMAC secrets.
* [ ] OpenTelemetry export for the SSE event stream.
* [ ] Docker Compose (orchestrator + gateway + frontend + Neo4j + Supabase emulator).
* [ ] Rust (Axum) gateway variant behind the same contract.

--

### License & Credits

Built as a demonstration-grade reference implementation of modern corrective, grounded, graph-native RAG patterns. Core ideas credit the CRAG, GraphRAG, contextual retrieval, RRF, and PageRank literature — implemented here as one coherent, runnable system.

















