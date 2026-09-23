"""Process-wide singletons: meta store, vector store, graph store, BM25, embedder."""
from __future__ import annotations

import asyncio

from aetheris.config import settings
from aetheris.embeddings import get_embedder
from aetheris.store.bm25 import BM25Index
from aetheris.store.graph_store import get_graph_store
from aetheris.store.meta_store import MetaStore, db_path_for
from aetheris.store.vector_store import get_vector_store


class Runtime:
    def __init__(self) -> None:
        self.meta = MetaStore(db_path_for(settings.DATA_DIR))
        self.vectors = get_vector_store()
        self.graph = get_graph_store()
        self.embedder = get_embedder()
        self.bm25 = BM25Index()
        self._bm25_lock = asyncio.Lock()
        self.bm25_dirty = True

    def rebuild_bm25(self) -> None:
        chunks = self.meta.all_chunks()
        self.bm25.build([(c["id"], c["embedded_text"]) for c in chunks])
        self.bm25_dirty = False

    async def ensure_bm25(self) -> None:
        if self.bm25_dirty:
            async with self._bm25_lock:
                if self.bm25_dirty:
                    self.rebuild_bm25()

    def chunk_lookup(self, chunk_ids: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for cid in chunk_ids:
            row = self.meta.get_chunk(cid)
            if row:
                out[cid] = row
        return out

    def info(self) -> dict:
        return {
            "meta": self.meta.stats(),
            "vector": self.vectors.info(),
            "graph": self.graph.stats(),
            "embedder": {"provider": self.embedder.provider, "model": self.embedder.model,
                         "dim": self.embedder.dim},
            "bm25_docs": self.bm25.N,
        }


_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime
