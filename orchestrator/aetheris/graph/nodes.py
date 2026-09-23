"""Agent nodes for the Aetheris LangGraph orchestration graph.

intent_router -> [web_fallback] -> retrieve (BM25+dense+PPR+communities, RRF)
  -> rerank (cross-encoder) -> grade (CRAG) <-> reformulate / web_fallback
  -> verify_grounding -> generate (streamed, cited, attested)
"""
from __future__ import annotations

import re
import time

from aetheris import llm
from aetheris.attribution import citation_record, content_digest
from aetheris.config import settings
from aetheris.graph.state import AgentState
from langchain_core.runnables import RunnableConfig
from aetheris.retrieval import rerank as rerank_mod
from aetheris.retrieval import sql_tool, web as web_mod
from aetheris.runtime import get_runtime
from aetheris.telemetry import NodeTrace, TelemetrySession
from aetheris.textutils import SYNONYMS, content_tokens, sentences

GLOBAL_WORDS = {
    "overall", "landscape", "themes", "theme", "summary", "summarize", "summarise",
    "big picture", "across", "trend", "trends", "compare", "comparison", "general",
    "macro", "ecosystem", "high level", "high-level", "holistic", "broader", "space",
}
RECENCY_WORDS = {
    "latest", "today", "now", "current", "currently", "recent", "recently", "news",
    "live", "right now", "this week", "this month",
}
REL_WORDS = {"relationship", "relate", "related", "connect", "connected", "depends",
             "dependency", "between", "interact", "link", "affects", "impact"}
ROUTE_PRIORITY = ["sql", "graph_global", "graph_local", "hybrid", "web", "vector"]


def _session(config) -> TelemetrySession:
    return config["configurable"]["session"]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


async def intent_router(state: AgentState, config: RunnableConfig) -> dict:
    """Semantic dispatch: score routes, pick one, publish the retrieval plan."""
    sess = _session(config)
    rt = get_runtime()
    q = state.get("active_query") or state.get("query", "")
    async with NodeTrace(sess, "intent_router"):
        scores: dict[str, float] = {"vector": 0.30, "graph_local": 0.0,
                                    "graph_global": 0.0, "sql": 0.0, "web": 0.0, "hybrid": 0.10}
        reasons: list[str] = []

        if sql_tool.is_sql_query(q):
            scores["sql"] += 0.95
            reasons.append("structured dispatch signal (aggregate/list intent detected)")

        seeds = rt.graph.find_seed_entities(q)
        if seeds:
            scores["graph_local"] += 0.55
            scores["hybrid"] += 0.45
            reasons.append("knowledge-graph entities matched: "
                           + ", ".join(s.replace('_', ' ') for s, _ in seeds[:4]))

        qw = _words(q)
        g_hits = sorted(w for w in GLOBAL_WORDS if w in qw or w in q.lower())
        if g_hits:
            scores["graph_global"] += min(0.35 + 0.1 * len(g_hits), 0.75)
            scores["hybrid"] += 0.15
            reasons.append(f"global/macro intent cues: {', '.join(g_hits[:4])}")

        r_hits = sorted(w for w in REL_WORDS if w in qw)
        if r_hits:
            scores["graph_local"] += 0.30
            reasons.append(f"relationship intent cues: {', '.join(r_hits[:4])}")

        w_hits = sorted(w for w in RECENCY_WORDS if w in qw or w in q.lower())
        if w_hits:
            scores["web"] += 0.60
            reasons.append(f"recency/live-data cues: {', '.join(w_hits[:4])}")

        if seeds and g_hits:
            scores["graph_global"] += 0.10

        mode = state.get("mode", "auto")
        if mode == "global":
            scores["graph_global"] += 1.0
            reasons.append("user forced mode=global (community search)")
        elif mode == "local":
            scores["graph_local"] += 1.0
            reasons.append("user forced mode=local (entity subgraph search)")

        route = max(sorted(scores), key=lambda r: (scores[r], -ROUTE_PRIORITY.index(r)
                                                   if r in ROUTE_PRIORITY else 0))
        plan = {"bm25": True, "dense": True, "ppr": False, "graph_local": False,
                "graph_global": False, "sql": False, "web": False}
        if route == "sql":
            plan["sql"] = True
            plan["ppr"] = bool(seeds)
            plan["graph_local"] = bool(seeds)
        elif route == "graph_global":
            plan["graph_global"] = True
            plan["ppr"] = bool(seeds)
            plan["graph_local"] = bool(seeds)
        elif route == "graph_local":
            plan.update({"ppr": True, "graph_local": True})
        elif route == "hybrid":
            plan.update({"ppr": True, "graph_local": True, "graph_global": bool(g_hits)})
        elif route == "web":
            plan["web"] = True
        if seeds and not plan["ppr"]:
            plan["ppr"] = True
        if not reasons:
            reasons.append("default dense+lexical dispatch (no stronger signal)")

        await sess.emit("route_selected", {
            "route": route, "scores": {k: round(v, 3) for k, v in scores.items()},
            "reasons": reasons, "plan": plan,
            "seeds": [s.replace('_', ' ') for s, _ in seeds[:6]],
        }, node="intent_router")
        return {"route": route, "route_scores": {k: round(v, 3) for k, v in scores.items()},
                "route_reasons": reasons, "retrieval_plan": plan,
                "steps": state.get("steps", 0) + 1}


async def web_fallback(state: AgentState, config: RunnableConfig) -> dict:
    """CRAG escape hatch: cascade to live web search when internal context fails."""
    sess = _session(config)
    async with NodeTrace(sess, "web_fallback"):
        if state.get("web_used") or not settings.CRAG_ENABLE_WEB_FALLBACK:
            await sess.emit("web_fallback", {"skipped": True,
                                             "reason": "already attempted or disabled"},
                            node="web_fallback")
            return {"degraded": True, "steps": state.get("steps", 0) + 1}
        q = state.get("active_query") or state.get("query", "")
        outcome = await web_mod.web_search(q)
        results = []
        for i, r in enumerate(outcome.get("results", []), start=1):
            text = f"{r.get('title', '')}. {r.get('snippet', '')}".strip()
            if not text:
                continue
            domain = re.sub(r"^www\.", "", (re.sub(r"^https?://", "", r.get("url", ""))).split("/")[0])
            results.append({
                "chunk_id": f"web::{i}",
                "doc_id": None,
                "title": r.get("title", "Web result"),
                "uri": r.get("url"),
                "header_path": domain,
                "text": text[:1200],
                "source": "web",
                "content_sha256": content_digest(text),
                "retrievers": {"web": i},
                "rrf_score": 1.0 / (settings.RRF_K + i),
            })
        await sess.emit("web_fallback", {
            "provider": outcome.get("provider"), "ok": outcome.get("ok"),
            "count": len(results), "error": outcome.get("error"),
            "reason": "context confidence below CRAG threshold"
            if state.get("grade") else "route=web (recency intent)",
            "results": [{"title": r["title"], "url": r["uri"]} for r in results[:5]],
        }, node="web_fallback")
        return {"web_results": results, "web_used": True,
                "web_info": {"provider": outcome.get("provider"), "count": len(results)},
                "steps": state.get("steps", 0) + 1}


def _rrf_add(scores: dict, ranks: dict, chunk_id: str, rank: int,
             weight: float, retriever: str) -> None:
    scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (settings.RRF_K + rank)
    ranks.setdefault(chunk_id, {})[retriever] = rank


async def retrieve(state: AgentState, config: RunnableConfig) -> dict:
    """Hybrid Retrieval Engine: BM25 + dense + PPR graph traversal + communities, fused by RRF."""
    sess = _session(config)
    rt = get_runtime()
    plan = state.get("retrieval_plan", {})
    aq = state.get("active_query") or state.get("query", "")
    pool = settings.RETRIEVAL_CANDIDATE_POOL
    async with NodeTrace(sess, "retrieve"):
        scores: dict[str, float] = {}
        ranks: dict[str, dict] = {}
        counts = {"bm25": 0, "dense": 0, "graph": 0, "community": 0, "web": 0}
        extra: dict[str, dict] = {}  # non-sqlite records (community/web summaries)

        # --- 1. lexical BM25 over header-injected chunk text ---
        if plan.get("bm25", True):
            await rt.ensure_bm25()
            for rank, (cid, sc) in enumerate(rt.bm25.search(aq, pool), start=1):
                _rrf_add(scores, ranks, cid, rank, settings.W_BM25, "bm25")
                counts["bm25"] += 1

        # --- 2. dense vector similarity ---
        if plan.get("dense", True):
            qv = rt.embedder.embed_query(aq)
            for rank, (cid, sc, _meta) in enumerate(rt.vectors.search(qv, pool), start=1):
                _rrf_add(scores, ranks, cid, rank, settings.W_DENSE, "dense")
                counts["dense"] += 1

        # --- 3. graph traversal: seed entities + Personalized PageRank ---
        seeds = rt.graph.find_seed_entities(aq)
        seed_names = [s for s, _ in seeds]
        ppr_entities: list[tuple[str, float]] = []
        if plan.get("ppr") and seed_names:
            ppr_entities = rt.graph.personalized_pagerank(seed_names)
            graph_chunk_ids = rt.graph.chunks_for_entities(
                seed_names + [n for n, _ in ppr_entities])
            for rank, cid in enumerate(graph_chunk_ids, start=1):
                _rrf_add(scores, ranks, cid, rank, settings.W_GRAPH, "graph")
                counts["graph"] += 1

        # --- 4a. local graph search: entity subgraph context ---
        graph_context: dict = {}
        if plan.get("graph_local") and seed_names:
            sub = rt.graph.subgraph_context(seed_names, hops=1)
            graph_context = {"mode": "local", "seeds": [s.replace('_', ' ') for s in seed_names],
                             "ppr": [{"entity": n.replace('_', ' '), "score": round(s, 4)}
                                     for n, s in ppr_entities[:8]],
                             "nodes": sub["nodes"][:40], "edges": sub["edges"][:60]}
            await sess.emit("graph_context", {"mode": "local",
                                              "seeds": graph_context["seeds"],
                                              "nodes": len(sub["nodes"]),
                                              "edges": len(sub["edges"])},
                            node="retrieve")

        # --- 4b. global graph search: community summaries as macro context ---
        if plan.get("graph_global"):
            comms = rt.meta.all_communities()
            graph_context = {**graph_context, "mode": "global",
                             "communities": [{"id": c["id"], "keywords": c["keywords"][:8],
                                              "size": c["size"]} for c in comms[:8]]}
            take = max(3, settings.RETRIEVAL_TOP_K // 2)
            for rank, comm in enumerate(comms[:take], start=1):
                cid = comm["id"]
                extra[cid] = {
                    "chunk_id": cid, "doc_id": None, "title": "Community summary",
                    "uri": None, "header_path": ", ".join(comm["keywords"][:6]),
                    "text": comm["summary"], "source": "community",
                    "content_sha256": content_digest(comm["summary"]),
                    "retrievers": {"community": rank},
                }
                _rrf_add(scores, ranks, cid, rank, settings.W_GRAPH, "community")
                counts["community"] += 1
            await sess.emit("graph_context", {"mode": "global",
                                              "communities": counts["community"]},
                            node="retrieve")

        # --- 5. structured SQL dispatch ---
        structured, structured_md = {}, ""
        if plan.get("sql"):
            structured = sql_tool.execute(aq)
            structured_md = sql_tool.render_markdown(structured)
            await sess.emit("sql_result", {
                "ok": structured.get("ok"), "label": structured.get("label"),
                "sql": structured.get("sql"),
                "rows": len(structured.get("rows", [])),
                "columns": structured.get("columns", []),
                "preview": structured.get("rows", [])[:5],
            }, node="retrieve")

        # --- 6. merge web fallback pseudo-chunks ---
        for i, wc in enumerate(state.get("web_results", []), start=1):
            extra[wc["chunk_id"]] = wc
            _rrf_add(scores, ranks, wc["chunk_id"], i, settings.W_DENSE * 1.2, "web")
            counts["web"] += 1

        # --- 7. weighted Reciprocal Rank Fusion ---
        fused_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        fused_ids = fused_ids[: max(settings.RETRIEVAL_TOP_K * 2, 16)]
        candidates: list[dict] = []
        for cid in fused_ids:
            if cid in extra:
                rec = {**extra[cid], "rrf_score": round(scores[cid], 5),
                       "retrievers": ranks.get(cid, {})}
            else:
                row = rt.meta.get_chunk(cid)
                if not row:
                    continue
                rec = {
                    "chunk_id": cid, "doc_id": row["doc_id"], "title": row.get("doc_title", ""),
                    "uri": row.get("doc_uri"), "header_path": row.get("header_path", ""),
                    "text": row.get("text", ""), "source": "internal",
                    "content_sha256": row.get("content_sha256") or content_digest(row.get("text", "")),
                    "retrievers": ranks.get(cid, {}),
                    "rrf_score": round(scores[cid], 5),
                }
            candidates.append(rec)

        await sess.emit("retrieval_fusion",
                        {"counts": counts, "fused": len(candidates), "rrf_k": settings.RRF_K,
                         "weights": {"bm25": settings.W_BM25, "dense": settings.W_DENSE,
                                     "graph": settings.W_GRAPH}},
                        node="retrieve")
        if settings.TELEMETRY_INCLUDE_CHUNKS:
            for i, c in enumerate(candidates[:12], start=1):
                await sess.emit("chunk_retrieved", {
                    "rank": i, "chunk_id": c["chunk_id"], "title": c["title"],
                    "header_path": c["header_path"], "source": c["source"],
                    "rrf_score": c.get("rrf_score", 0), "retrievers": c.get("retrievers", {}),
                    "snippet": (c.get("text") or "")[:180],
                }, node="retrieve")


        return {"candidates": candidates, "retrieval_counts": counts,
                "structured": structured, "structured_md": structured_md,
                "graph_context": graph_context,
                "steps": state.get("steps", 0) + 1}


async def rerank_node(state: AgentState, config: RunnableConfig) -> dict:
    """Cross-encoder rerank of fused candidates (Flashrank / Cohere / heuristic)."""
    sess = _session(config)
    aq = state.get("active_query") or state.get("query", "")
    async with NodeTrace(sess, "rerank"):
        out = await rerank_mod.rerank(aq, state.get("candidates", []))
        results = out["results"]
        await sess.emit("rerank_complete", {
            "provider": out["provider"], "top_k": len(results),
            "results": [{"rank": i, "chunk_id": c["chunk_id"], "title": c.get("title", ""),
                         "score": c.get("rerank_score", 0), "raw": c.get("rerank_raw", 0),
                         "source": c.get("source", "internal")}
                        for i, c in enumerate(results, start=1)],
        }, node="rerank")
        keep_ids = {r["chunk_id"] for r in results}
        rejected = [{"chunk_id": c["chunk_id"], "title": c.get("title", ""),
                     "score": c.get("rerank_score", 0),
                     "reason": "below rerank cut-off (did not enter top-k)"}
                    for c in state.get("candidates", []) if c["chunk_id"] not in keep_ids]
        return {"reranked": results, "rerank_provider": out["provider"],
                "rejected": rejected, "steps": state.get("steps", 0) + 1}


async def grade(state: AgentState, config: RunnableConfig) -> dict:
    """Corrective RAG grader: confidence scoring + per-chunk accept/reject telemetry."""
    sess = _session(config)
    aq = state.get("active_query") or state.get("query", "")
    async with NodeTrace(sess, "grade"):
        chunks = state.get("reranked", [])
        q_tokens = set(content_tokens(aq))
        threshold = settings.CRAG_CONFIDENCE_THRESHOLD
        graded: list[dict] = []

        union: set[str] = set()
        doc_ids: set[str] = set()
        raws: list[float] = []
        for c in chunks:
            union |= set(content_tokens(c.get("text", "")))
            doc_ids.add(str(c.get("doc_id") or c.get("uri") or c.get("header_path", "web")))
            raws.append(float(c.get("rerank_raw", c.get("rerank_score", 0.0))))

        coverage = (len(q_tokens & union) / len(q_tokens)) if q_tokens else 0.0
        diversity = min(1.0, len(doc_ids) / 2.0)
        top3 = sum(sorted(raws, reverse=True)[:3]) / min(len(raws), 3) if raws else 0.0
        confidence = max(0.0, min(1.0, 0.45 * top3 + 0.35 * coverage + 0.20 * diversity))

        floor = 0.18
        any_accepted = False
        for i, c in enumerate(chunks, start=1):
            raw = float(c.get("rerank_raw", c.get("rerank_score", 0.0)))
            accepted = raw >= floor
            any_accepted = any_accepted or accepted
            reason = (f"raw relevance {raw:.2f} ≥ floor {floor:.2f} — ACCEPTED"
                      if accepted else
                      f"raw relevance {raw:.2f} < floor {floor:.2f} — REJECTED as weak evidence")
            graded.append({**c, "accepted": accepted, "grade_reason": reason})
            await sess.emit("chunk_graded", {
                "chunk_id": c["chunk_id"], "rank": i, "accepted": accepted,
                "score": round(raw, 4), "normalized": c.get("rerank_score", 0),
                "reason": reason, "title": c.get("title", ""),
                "source": c.get("source", "internal"),
            }, node="grade")

        passed = bool(chunks) and any_accepted and confidence >= threshold
        await sess.emit("grade_result", {
            "confidence": round(confidence, 4), "threshold": threshold, "passed": passed,
            "coverage": round(coverage, 4), "diversity": round(diversity, 4),
            "top_relevance": round(top3, 4), "chunks": len(chunks),
            "strategy": "CRAG corrective loop",
        }, node="grade")
        return {"reranked": graded,
                "grade": {"confidence": round(confidence, 4), "threshold": threshold,
                          "passed": passed, "coverage": round(coverage, 4)},
                "steps": state.get("steps", 0) + 1}


def _variants(query: str) -> list[tuple[str, str]]:
    """Deterministic reformulation strategies tried in order."""
    rt = get_runtime()
    out: list[tuple[str, str]] = []
    seeds = rt.graph.find_seed_entities(query, limit=4)
    if seeds:
        v = " ".join(s.replace("_", " ") for s, _ in seeds)
        out.append(("entity_focus", v))
    keywords = content_tokens(query)
    if keywords:
        out.append(("keyword_strip", " ".join(keywords)))
        expanded: list[str] = []
        for t in keywords:
            expanded.append(t)
            expanded.extend(SYNONYMS.get(t, []))
        if len(expanded) > len(keywords):
            out.append(("synonym_expand", " ".join(dict.fromkeys(expanded))))
    return [(s, v.strip()) for s, v in out if v.strip()]


async def reformulate(state: AgentState, config: RunnableConfig) -> dict:
    """Query reformulation loop — next unused strategy variant (LLM-assisted first try)."""
    sess = _session(config)
    before = state.get("active_query") or state.get("query", "")
    async with NodeTrace(sess, "reformulate"):
        tried = list(state.get("tried_queries", []))
        attempt = state.get("reformulation_count", 0) + 1
        strategy, after = "", ""

        if attempt == 1 and llm.llm_available():
            try:
                cand = await llm.chat(
                    [{"role": "user", "content":
                        "Rewrite this retrieval query to maximize recall over an internal "
                        "knowledge base. Return ONLY the rewritten query, max 16 words.\n"
                        f"Query: {before}"}],
                    temperature=0.3, max_tokens=80,
                )
                cand = cand.strip().strip('"')
                if 3 <= len(cand) <= 300 and cand not in tried and cand != before:
                    strategy, after = "llm_rewrite", cand
            except Exception:
                strategy, after = "", ""

        if not after:
            for s, v in _variants(before):
                if v not in tried and v != before:
                    strategy, after = s, v
                    break
        if not after:
            strategy, after = "fallback_keyword_strip", " ".join(content_tokens(before)) or before

        tried.append(after)
        await sess.emit("query_reformulated", {
            "attempt": attempt, "strategy": strategy, "before": before, "after": after,
            "remaining": max(settings.CRAG_MAX_REFORMULATIONS - attempt, 0),
        }, node="reformulate")
        return {"active_query": after, "tried_queries": tried,
                "reformulation_count": attempt, "steps": state.get("steps", 0) + 1}


async def verify_grounding(state: AgentState, config: RunnableConfig) -> dict:
    """Grounding verification: can every query aspect be traced to context + attestation?"""
    sess = _session(config)
    rt = get_runtime()
    aq = state.get("active_query") or state.get("query", "")
    async with NodeTrace(sess, "verify_grounding"):
        chunks = [c for c in state.get("reranked", []) if c.get("accepted", True)]
        union = " ".join(c.get("text", "") for c in chunks).lower()
        union_tokens = set(content_tokens(union))

        aspects: list[dict] = []
        seeds = rt.graph.find_seed_entities(aq, limit=3)
        for name, _score in seeds:
            aspects.append({"aspect": name.replace("_", " "), "kind": "entity"})
        for tok in content_tokens(aq)[:4]:
            if len(tok) > 3:
                aspects.append({"aspect": tok, "kind": "keyword"})
        if not aspects:
            aspects = [{"aspect": aq[:60], "kind": "query", "supported": True}]
        aspects = aspects[:5]

        supported = 0
        for a in aspects:
            needle = a["aspect"].lower()
            tokens = needle.split()
            a["supported"] = all(t in union for t in tokens) if len(tokens) > 1 else needle in union
            if a["supported"]:
                supported += 1

        structured_ok = bool(state.get("structured", {}).get("ok"))
        if structured_ok:
            supported += 1
            aspects.append({"aspect": "structured SQL result", "kind": "structured",
                            "supported": True})
        if state.get("web_used") and state.get("web_results"):
            supported += 1
            aspects.append({"aspect": "live web evidence", "kind": "web", "supported": True})

        total = max(len(aspects), 1)
        score = max(0.0, min(1.0, supported / total))
        threshold = settings.GROUNDING_MIN_SCORE
        passed = score >= threshold and bool(chunks or structured_ok)

        # attestability: every context piece must carry a content digest
        missing_digest = [c["chunk_id"] for c in chunks if not c.get("content_sha256")]
        for c in chunks:
            if not c.get("content_sha256"):
                c["content_sha256"] = content_digest(c.get("text", ""))

        repairs = state.get("grounding_repairs", 0)
        degraded = state.get("degraded", False)
        if not passed:
            repairs += 1
            if repairs >= settings.GROUNDING_MAX_REPAIRS:
                degraded = True

        await sess.emit("grounding_check", {
            "score": round(score, 4), "threshold": threshold, "passed": passed,
            "aspects": aspects, "repairs": repairs,
            "missing_digest": len(missing_digest),
            "note": "context can ground the answer" if passed
            else "context insufficient — repair loop engaged" if not degraded
            else "repairs exhausted — proceeding in degraded mode",
        }, node="verify_grounding")
        return {"grounding": {"score": round(score, 4), "threshold": threshold,
                              "passed": passed, "aspects": aspects},
                "reranked": chunks, "grounding_repairs": repairs, "degraded": degraded,
                "steps": state.get("steps", 0) + 1}


_SYSTEM = (
    "You are Aetheris Core, an autonomous enterprise intelligence engine. "
    "Answer STRICTLY from the numbered CONTEXT blocks. Rules:\n"
    "1. Every factual sentence MUST end with a citation marker like [1] or [2][3] "
    "referring to the CONTEXT block index.\n"
    "2. Never invent facts, numbers or sources that are not in CONTEXT.\n"
    "3. If CONTEXT lacks the answer, say exactly: 'Not found in the internal knowledge mesh.'\n"
    "4. Use tight Markdown: a 1-3 sentence lead, then bullets or a short table if useful.\n"
    "5. When [SQL] or [GRAPH] blocks exist, treat them as authoritative structured evidence."
)


def _audit(answer: str, context_text: str) -> dict:
    """Post-hoc grounding audit: fraction of answer sentences backed by context."""
    ctx = set(content_tokens(context_text))
    total, supported = 0, 0
    for s in sentences(answer):
        if len(content_tokens(s)) < 4:
            continue
        total += 1
        if re.search(r"\[\d+\]", s):
            supported += 1
            continue
        toks = content_tokens(s)
        overlap = sum(1 for t in toks if t in ctx) / max(len(toks), 1)
        if overlap >= 0.4:
            supported += 1
    ratio = (supported / total) if total else 1.0
    return {"support_ratio": round(ratio, 4), "sentences": total,
            "supported": supported,
            "passed": ratio >= settings.GROUNDING_MIN_SCORE or total == 0}


async def generate(state: AgentState, config: RunnableConfig) -> dict:
    """Stream the final cited answer (LLM or extractive fallback) + attested citations."""
    sess = _session(config)
    request_id = state.get("request_id", "")
    original = state.get("original_query") or state.get("query", "")
    degraded = bool(state.get("degraded", False))
    async with NodeTrace(sess, "generate"):
        chunks = [c for c in state.get("reranked", []) if c.get("accepted", True)]
        if not chunks:
            chunks = state.get("reranked", [])[:3]

        context_blocks: list[str] = []
        citations: list[dict] = []
        for i, c in enumerate(chunks, start=1):
            digest = c.get("content_sha256") or content_digest(c.get("text", ""))
            c["content_sha256"] = digest
            citations.append(citation_record(
                chunk_id=c["chunk_id"], content_sha256=digest, request_id=request_id,
                index=i, title=c.get("title") or "Untitled",
                header_path=c.get("header_path", ""), source=c.get("source", "internal"),
                uri=c.get("uri"), snippet=(c.get("text") or "")[:280],
            ))
            header = f" — {c['header_path']}" if c.get("header_path") else ""
            tag = "web" if c.get("source") == "web" else (
                "community" if c.get("source") == "community" else "internal")
            context_blocks.append(
                f"[{i}] {c.get('title', 'Untitled')} ({tag}){header}\n{c.get('text', '')}"
            )

        if state.get("structured_md"):
            context_blocks.append("[SQL] Structured evidence:\n" + state["structured_md"])
        gc = state.get("graph_context") or {}
        if gc.get("mode") == "local" and gc.get("nodes"):
            context_blocks.append(
                "[GRAPH] Entity subgraph (local search) — seeds: "
                + ", ".join(gc.get("seeds", []))
                + "; related entities: "
                + ", ".join(n.get("name", n.get("id", "")) for n in gc["nodes"][:10])
            )
        elif gc.get("mode") == "global":
            comms = gc.get("communities", [])
            context_blocks.append(
                "[GRAPH] Community themes (global search): "
                + "; ".join(", ".join(c.get("keywords", [])[:5]) for c in comms[:5])
            )
        if state.get("web_info"):
            context_blocks.append(
                f"[NOTE] Live web fallback engaged ({state['web_info'].get('count', 0)} results)."
            )
        context = "\n\n".join(context_blocks)

        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {original}"},
        ]

        buf = ""
        provider = "extractive-fallback"
        if llm.llm_available():
            provider = settings.LLM_MODEL
            try:
                async for delta in llm.stream_chat(messages):
                    buf += delta
                    await sess.emit("answer_delta", {"text": delta}, node="generate")
            except Exception as exc:
                buf = ""
                await sess.emit("error", {"stage": "generate", "message": str(exc),
                                          "action": "falling back to extractive generator"},
                                node="generate")
        if not buf:
            provider = "extractive-fallback"
            async for delta in llm.extractive_answer(original, chunks, degraded=degraded):
                buf += delta
                await sess.emit("answer_delta", {"text": delta}, node="generate")

        audit = _audit(buf, context)
        await sess.emit("grounding_audit", audit, node="generate")
        await sess.emit("answer", {
            "text": buf, "citations": citations, "provider": provider,
            "degraded": degraded, "route": state.get("route", ""),
            "confidence": state.get("grade", {}).get("confidence"),
            "grounding_score": state.get("grounding", {}).get("score"),
            "web_used": bool(state.get("web_used")),
            "reformulations": state.get("reformulation_count", 0),
            "audit": audit,
        }, node="generate")
        return {"answer": buf, "citations": citations}






