"""End-to-end ingestion pipeline (contextual headers -> embeddings -> dual index)."""
from __future__ import annotations

import time

from aetheris import llm
from aetheris.config import settings
from aetheris.ingest.chunker import chunk_document
from aetheris.ingest.extractor import extract
from aetheris.runtime import get_runtime
from aetheris.textutils import sha256_hex, sentences


def _extractive_summary(members: list[str], keywords: list[str], texts: list[str]) -> str:
    head = (f"Community of {len(members)} entities — "
            + ", ".join(m.replace('_', ' ') for m in members[:10])
            + ("…" if len(members) > 10 else "") + ".")
    themes = ("Dominant themes: " + ", ".join(keywords[:8]) + ".") if keywords else ""
    quotes = []
    for t in texts[:3]:
        sents = sentences(t)
        if sents:
            quotes.append(sents[0])
    body = " ".join(quotes[:2])
    return " ".join(p for p in (head, themes, body) if p).strip()


async def rebuild_communities() -> dict:
    """Recompute graph communities + their summaries (global-search corpus)."""
    rt = get_runtime()
    raw = rt.graph.communities()
    clean: list[dict] = []
    use_llm = llm.llm_available()
    for comm in raw[:20]:
        keywords = comm.get("keywords", [])
        texts = comm.get("_texts", [])
        summary = ""
        if use_llm and texts:
            try:
                summary = await llm.chat(
                    [{"role": "user", "content":
                        "Summarize this knowledge-graph community in <=3 sentences for a "
                        "global-search RAG corpus. Entities: "
                        + ", ".join(comm["members"][:15])
                        + "\n\nEvidence excerpts:\n" + "\n---\n".join(t[:900] for t in texts[:4])}],
                    temperature=0.1, max_tokens=300,
                )
            except Exception:
                summary = ""
        if not summary:
            summary = _extractive_summary(comm["members"], keywords, texts)
        clean.append({"id": comm["id"], "level": comm.get("level", 0),
                      "members": comm["members"], "keywords": keywords, "summary": summary})
    rt.meta.replace_communities(clean)
    return {"communities": len(clean)}


async def ingest_document(title: str, text: str, source: str = "manual",
                          uri: str | None = None, meta: dict | None = None) -> dict:
    rt = get_runtime()
    t0 = time.time()
    text = (text or "").strip()
    if not text:
        return {"doc_id": None, "skipped": True, "reason": "empty document"}
    doc_sha = sha256_hex(f"{title}\n{text}")
    doc_id = f"doc::{doc_sha[:12]}"
    old_ids = [c["id"] for c in rt.meta.list_chunks_for_doc(doc_id)]

    # 1. heading-aware chunking + contextual header injection
    chunks = chunk_document(text, doc_id, title)
    if not chunks:
        return {"doc_id": doc_id, "skipped": True, "reason": "no chunkable content"}
    chunk_dicts = [c.as_dict() for c in chunks]

    # 2. persist source of truth
    rt.meta.upsert_document(doc_id, title, source, uri, doc_sha, meta or {})
    rt.meta.replace_chunks(doc_id, chunk_dicts)

    # 3. embed (header-injected text) into the vector engine
    if old_ids:
        rt.vectors.delete(old_ids)
    vectors = rt.embedder.embed([c.embedded_text for c in chunks])
    rt.vectors.upsert([
        {
            "chunk_id": c.id,
            "vector": v,
            "meta": {"doc_id": doc_id, "header_path": c.header_path,
                     "text": c.text[:2000], "title": title},
        }
        for c, v in zip(chunks, vectors)
    ])

    # 4. entity/relation extraction -> knowledge graph
    ext = await extract(text, chunk_dicts)
    entity_ids = rt.meta.upsert_entities(doc_id, ext.entities)
    links: list[tuple[str, str]] = []
    for norm, cids in ext.entity_chunk.items():
        eid = entity_ids.get(norm)
        if eid:
            links.extend((eid, cid) for cid in cids)
    rt.meta.link_entity_chunks(links)
    rel_count = rt.meta.upsert_relationships(doc_id, ext.relationships, entity_ids, ext.entity_chunk)
    rt.graph.sync_document(
        doc_id, ext.entities, ext.relationships, entity_ids, ext.entity_chunk,
        {c["id"]: c["text"] for c in chunk_dicts},
    )

    # 5. lexical index + community refresh
    rt.rebuild_bm25()
    comm = await rebuild_communities()

    return {
        "doc_id": doc_id,
        "title": title,
        "sha256": doc_sha,
        "chunks": len(chunks),
        "tokens": sum(c["token_count"] for c in chunk_dicts),
        "entities": len(ext.entities),
        "relationships": rel_count,
        "extraction_method": ext.method,
        "embedding_provider": rt.embedder.provider,
        "vector_backend": rt.vectors.backend,
        "graph_backend": rt.graph.backend,
        **comm,
        "elapsed_ms": round((time.time() - t0) * 1000, 1),
    }


async def wipe_all() -> dict:
    rt = get_runtime()
    all_ids = [c["id"] for c in rt.meta.all_chunks()]
    rt.meta.wipe()
    if all_ids:
        rt.vectors.delete(all_ids)
    rt.graph.wipe()
    rt.rebuild_bm25()
    rt.meta.replace_communities([])
    return {"wiped": True, "removed_chunks": len(all_ids)}
