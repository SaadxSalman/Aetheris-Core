"""FastAPI application: SSE agent stream + ingestion + inspection endpoints."""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aetheris import __version__
from aetheris.attribution import verify as verify_attestation
from aetheris.config import public_config, settings
from aetheris.demo_data import DEMO_DOCUMENTS
from aetheris.graph.builder import get_graph
from aetheris.graph.state import initial_state
from aetheris.ingest.pipeline import ingest_document, wipe_all
from aetheris.runtime import get_runtime
from aetheris.telemetry import TelemetrySession


@asynccontextmanager
async def lifespan(app: FastAPI):
    rt = get_runtime()
    rt.rebuild_bm25()
    # Seed demo docs when the corpus is empty, OR repair a partial ingestion
    # (e.g. a crash between SQLite writes and vector upserts). Ingest is
    # idempotent — document IDs are content-hashed.
    stats = rt.meta.stats()
    needs_seed = stats["documents"] == 0 or (rt.vectors.count() == 0 and stats["chunks"] > 0)
    if settings.SEED_DEMO_CORPUS and needs_seed:
        for doc in DEMO_DOCUMENTS:
            await ingest_document(title=doc["title"], text=doc["text"],
                                  source=doc["source"], uri=doc.get("uri"),
                                  meta={"seeded": True})
        rt.rebuild_bm25()
    yield



app = FastAPI(
    title="Aetheris Core — Orchestrator",
    description="Autonomous Multi-Modal Polyglot GraphRAG Engine",
    version=__version__,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: str = "auto"  # auto | local | global
    request_id: str | None = None


class IngestBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=500_000)
    source: str = "manual"
    uri: str | None = None
    meta: dict | None = None


class CitationBody(BaseModel):
    chunk_id: str
    content_sha256: str
    request_id: str
    attestation: str


@app.get("/api/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__, "ts": time.time()}


@app.get("/api/v1/config")
async def config() -> dict:
    return public_config()


@app.get("/api/v1/stats")
async def stats() -> dict:
    rt = get_runtime()
    return {"meta": rt.meta.stats(), "vector": rt.vectors.info(),
            "graph": rt.graph.stats(), "embedder": {"provider": rt.embedder.provider,
                                                    "model": rt.embedder.model,
                                                    "dim": rt.embedder.dim},
            "bm25_docs": rt.bm25.N}


@app.post("/api/v1/query")
async def query_endpoint(body: QueryBody) -> StreamingResponse:
    """Run the LangGraph agent loop and stream telemetry + answer as SSE."""
    request_id = body.request_id or f"req_{uuid.uuid4().hex[:12]}"
    session = TelemetrySession(request_id, settings.TELEMETRY_MAX_EVENTS,
                               settings.SSE_HEARTBEAT_SECONDS)
    state = initial_state(body.query.strip(), request_id, body.mode)
    graph = get_graph()
    await session.emit("run_start", {"request_id": request_id, "query": state["query"],
                                     "mode": body.mode})

    async def runner() -> None:
        t0 = time.time()
        try:
            await graph.ainvoke(
                state,
                config={"configurable": {"session": session, "request_id": request_id}},
            )
            await session.emit("run_end", {"request_id": request_id,
                                           "elapsed_ms": round((time.time() - t0) * 1000, 2),
                                           "status": "ok"})
        except Exception as exc:  # pragma: no cover
            await session.emit("error", {"stage": "graph", "message": str(exc)})
            await session.emit("run_end", {"request_id": request_id,
                                           "elapsed_ms": round((time.time() - t0) * 1000, 2),
                                           "status": "error"})
        finally:
            session.close()

    async def event_stream():
        task = asyncio.create_task(runner())
        async for frame in session.stream():
            yield frame
        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
        },
    )


@app.post("/api/v1/ingest")
async def ingest_endpoint(body: IngestBody) -> dict:
    report = await ingest_document(title=body.title, text=body.text, source=body.source,
                                   uri=body.uri, meta=body.meta)
    if report.get("skipped"):
        raise HTTPException(status_code=422, detail=report)
    return report


@app.get("/api/v1/corpus")
async def corpus() -> dict:
    rt = get_runtime()
    docs = rt.meta.list_documents()
    return {"documents": docs, "count": len(docs), "stats": rt.meta.stats()}


@app.delete("/api/v1/corpus")
async def reset_corpus() -> dict:
    return await wipe_all()


@app.get("/api/v1/graph")
async def graph_view() -> dict:
    """Knowledge-graph projection (entities, typed edges, communities) for the UI."""
    rt = get_runtime()
    entities = rt.meta.all_entities()
    rels = rt.meta.all_relationships()
    comm_sizes = {c["id"]: c["size"] for c in rt.meta.all_communities()}
    nodes = [
        {"id": e["id"], "label": e["name"], "type": e["type"],
         "mentions": e["mentions"], "links": e.get("chunk_links", 0)}
        for e in sorted(entities, key=lambda x: -x["mentions"])[:120]
    ]
    node_ids = {n["id"] for n in nodes}
    edges = [
        {"id": r["id"], "source": r["src"], "target": r["dst"], "type": r["type"],
         "weight": r["weight"]}
        for r in rels if r["src"] in node_ids and r["dst"] in node_ids
    ][:240]
    stats = rt.graph.stats()
    return {"nodes": nodes, "edges": edges, "stats": stats,
            "communities": rt.meta.all_communities(), "community_sizes": comm_sizes}


@app.get("/api/v1/chunks/{chunk_id}")
async def get_chunk(chunk_id: str) -> dict:
    row = get_runtime().meta.get_chunk(chunk_id)
    if not row:
        raise HTTPException(status_code=404, detail="chunk not found")
    return row


@app.post("/api/v1/verify-citation")
async def verify_citation(body: CitationBody) -> dict:
    ok = verify_attestation(body.chunk_id, body.content_sha256, body.request_id,
                            body.attestation)
    row = get_runtime().meta.get_chunk(body.chunk_id)
    return {
        "valid": ok,
        "chunk_id": body.chunk_id,
        "chunk_exists": row is not None,
        "expected_content_sha256": row.get("content_sha256") if row else None,
        "provided_content_sha256": body.content_sha256,
        "content_match": bool(row) and row.get("content_sha256") == body.content_sha256,
    }


