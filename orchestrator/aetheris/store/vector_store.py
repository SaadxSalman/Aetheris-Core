"""Vector backends: Supabase (pgvector) via REST  |  local in-process cosine index."""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path

import httpx

from aetheris.config import settings


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class LocalVectorStore:
    """In-memory cosine index persisted to vectors.json after every write batch."""

    backend = "local"

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, dict] = {}
        if path.exists():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                self._vectors = blob.get("vectors", {})
                self._meta = blob.get("meta", {})
            except Exception:
                self._vectors, self._meta = {}, {}

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"vectors": self._vectors, "meta": self._meta}),
            encoding="utf-8",
        )

    def upsert(self, items: list[dict]) -> None:
        """items: [{chunk_id, vector, meta}]"""
        with self._lock:
            for it in items:
                self._vectors[it["chunk_id"]] = [float(x) for x in it["vector"]]
                self._meta[it["chunk_id"]] = it.get("meta", {})
            self._persist()

    def search(self, vector: list[float], k: int = 10) -> list[tuple[str, float, dict]]:
        with self._lock:
            scored = [
                (cid, _cosine(vector, vec), self._meta.get(cid, {}))
                for cid, vec in self._vectors.items()
            ]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def delete(self, chunk_ids: list[str]) -> None:
        with self._lock:
            for cid in chunk_ids:
                self._vectors.pop(cid, None)
                self._meta.pop(cid, None)
            self._persist()

    def count(self) -> int:
        return len(self._vectors)

    def info(self) -> dict:
        dim = len(next(iter(self._vectors.values()))) if self._vectors else 0
        return {"backend": "local", "vectors": self.count(), "dim": dim}


class SupabaseVectorStore:
    """pgvector similarity via Supabase PostgREST (table + match RPC)."""

    backend = "supabase"

    def __init__(self) -> None:
        self.base = settings.SUPABASE_URL.rstrip("/")
        self.table = settings.SUPABASE_VECTOR_TABLE
        self.rpc = settings.SUPABASE_MATCH_RPC
        self.schema = settings.SUPABASE_SCHEMA
        key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
        }

    def upsert(self, items: list[dict]) -> None:
        rows = [
            {
                "chunk_id": it["chunk_id"],
                "doc_id": it.get("meta", {}).get("doc_id"),
                "header_path": it.get("meta", {}).get("header_path", ""),
                "text": it.get("meta", {}).get("text", ""),
                "embedding": [float(x) for x in it["vector"]],
            }
            for it in items
        ]
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base}/rest/v1/{self.table}",
                json=rows,
                headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            resp.raise_for_status()

    def search(self, vector: list[float], k: int = 10) -> list[tuple[str, float, dict]]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base}/rest/v1/rpc/{self.rpc}",
                json={"query_embedding": [float(x) for x in vector], "match_count": k},
                headers=self._headers,
            )
            resp.raise_for_status()
            rows = resp.json()
        return [
            (r.get("chunk_id"), float(r.get("similarity", 0.0)),
             {"doc_id": r.get("doc_id"), "header_path": r.get("header_path", ""),
              "text": r.get("text", "")})
            for r in rows
        ]

    def delete(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                "DELETE",
                f"{self.base}/rest/v1/{self.table}",
                params={"chunk_id": f"in.({','.join(chunk_ids)})"},
                headers=self._headers,
            )
            resp.raise_for_status()

    def count(self) -> int:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base}/rest/v1/{self.table}",
                params={"select": "chunk_id", "limit": "100000"},
                headers=self._headers,
            )
            resp.raise_for_status()
            return len(resp.json())

    def info(self) -> dict:
        try:
            return {"backend": "supabase", "vectors": self.count()}
        except Exception as exc:  # pragma: no cover
            return {"backend": "supabase", "error": str(exc)}


_vector_store = None


def get_vector_store():
    """Lazy singleton honoring VECTOR_BACKEND=auto|supabase|local."""
    global _vector_store
    if _vector_store is None:
        mode = settings.VECTOR_BACKEND
        use_supabase = mode == "supabase" or (
            mode == "auto" and settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY
        )
        if use_supabase:
            try:
                store = SupabaseVectorStore()
                store.count()  # connectivity probe
                _vector_store = store
            except Exception:
                _vector_store = LocalVectorStore(settings.DATA_DIR / "vectors.json")
        else:
            _vector_store = LocalVectorStore(settings.DATA_DIR / "vectors.json")
    return _vector_store

