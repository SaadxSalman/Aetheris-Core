"""Embedding providers: deterministic local hashed embedder + OpenAI-compatible API."""
from __future__ import annotations

import hashlib
import math
import re

import httpx

from aetheris.config import settings

_WORD_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_'-]*")

_QUERY_PREFIXES = ("bge", "arctic", "gte-", "jina", "e5")


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class LocalHashEmbedder:
    """Deterministic hashed bag-of-words + char-ngram embedder (offline fallback).

    Quality is surprisingly decent for retrieval over a small corpus: content
    words dominate the vector, so cosine similarity tracks lexical semantics.
    """

    provider = "local"

    def __init__(self, dim: int = 384):
        self.dim = dim

    @staticmethod
    def _bucket(token: str, dim: int, seed: str) -> int:
        h = hashlib.blake2b(f"{seed}:{token}".encode(), digest_size=8).digest()
        return int.from_bytes(h, "big") % dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            words = [w.lower() for w in _WORD_RE.findall(text)]
            for w in words:
                vec[self._bucket(w, self.dim, "w")] += 1.0
                if len(w) > 4:  # light morphology: plural/stem robustness
                    vec[self._bucket(w[:-1], self.dim, "s")] += 0.5
            # character trigrams capture fuzzy matches / typos
            joined = " " + " ".join(words) + " "
            for i in range(len(joined) - 2):
                tri = joined[i:i + 3]
                if tri.strip():
                    vec[self._bucket(tri, self.dim, "c")] += 0.25
            out.append(_l2_normalize(vec))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OpenAICompatEmbedder:
    """BGE-M3 / Snowflake Arctic / OpenAI / TEI ... any /embeddings endpoint."""

    provider = "openai_compatible"

    def __init__(self) -> None:
        self.base = settings.EMBEDDING_BASE_URL.rstrip("/")
        self.model = settings.EMBEDDING_MODEL
        self.api_key = settings.EMBEDDING_API_KEY
        self.dim = settings.EMBEDDING_DIM
        self._detected = False

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self.model, "input": texts}
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self.base}/embeddings", json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()["data"]
        vectors = [_l2_normalize(item["embedding"]) for item in sorted(data, key=lambda d: d["index"])]
        if vectors and not self._detected:
            self.dim = len(vectors[0])
            self._detected = True
        return vectors

    def embed_query(self, text: str) -> list[float]:
        low = self.model.lower()
        if any(p in low for p in _QUERY_PREFIXES):
            text = "Represent this sentence for searching relevant passages: " + text
        return self.embed([text])[0]


class Embedder:
    """Facade with graceful degradation: API failures fall back to local hashing."""

    def __init__(self) -> None:
        self._local = LocalHashEmbedder(settings.EMBEDDING_DIM)
        self._remote: OpenAICompatEmbedder | None = None
        if settings.EMBEDDER_PROVIDER == "openai_compatible" and (
            settings.EMBEDDING_API_KEY or settings.EMBEDDING_BASE_URL
        ):
            self._remote = OpenAICompatEmbedder()
        self.provider = self._remote.provider if self._remote else "local"
        self.model = settings.EMBEDDING_MODEL if self._remote else f"local-hash-{settings.EMBEDDING_DIM}"
        self.dim = self._remote.dim if self._remote else settings.EMBEDDING_DIM

    @property
    def mode(self) -> str:
        return self.provider

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._remote:
            try:
                vecs = self._remote.embed(texts)
                self.dim = len(vecs[0]) if vecs else self.dim
                return vecs
            except Exception:
                # degrade silently to local hashing so ingestion never blocks
                self.provider = "local-fallback"
        return self._local.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._remote:
            try:
                vec = self._remote.embed_query(text)
                self.dim = len(vec)
                return vec
            except Exception:
                self.provider = "local-fallback"
        return self._local.embed_query(text)


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
