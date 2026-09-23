"""Shared text processing helpers (tokenizer, hashing, normalization)."""
from __future__ import annotations

import hashlib
import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "to", "in",
    "on", "at", "by", "for", "with", "about", "as", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "this", "that", "these", "those", "from",
    "into", "up", "down", "out", "so", "than", "too", "very", "can", "will",
    "just", "do", "does", "did", "done", "how", "what", "why", "when", "where",
    "who", "which", "whom", "whose", "isn", "aren", "wasn", "weren", "has", "have",
    "had", "not", "no", "you", "your", "we", "our", "they", "them", "their", "i",
    "me", "my", "he", "she", "him", "her", "his", "please", "tell", "give", "show",
    "me", "any", "all", "some", "more", "most", "other", "over", "under", "again",
    "there", "here", "also", "into", "via", "per", "each", "many", "much", "get",
    "got", "make", "made", "like", "well", "back", "only", "own", "same", "s", "t",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-'_+]*", re.IGNORECASE)
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[])")
_WS_RE = re.compile(r"\s+")


def sha256_hex(text: str, pepper: str = "") -> str:
    h = hashlib.sha256()
    if pepper:
        h.update(pepper.encode("utf-8"))
    h.update(text.encode("utf-8", errors="replace"))
    return h.hexdigest()


def short_hash(text: str, n: int = 10) -> str:
    return sha256_hex(text)[:n]


def normalize_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def tokenize(text: str, drop_stopwords: bool = False) -> list[str]:
    toks = [t.lower() for t in _TOKEN_RE.findall(text)]
    if drop_stopwords:
        toks = [t for t in toks if t not in STOPWORDS and len(t) > 1]
    return toks


def sentences(text: str) -> list[str]:
    parts = _SENT_RE.split(normalize_ws(text))
    return [p.strip() for p in parts if p.strip()]


def content_tokens(text: str) -> list[str]:
    return tokenize(text, drop_stopwords=True)


def overlap_ratio(a_tokens: list[str], b_tokens: list[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    bset = set(b_tokens)
    hit = sum(1 for t in a_tokens if t in bset)
    return hit / len(a_tokens)


SYNONYMS: dict[str, list[str]] = {
    "rag": ["retrieval", "augmented", "generation"],
    "llm": ["language", "model"],
    "graphrag": ["graph", "knowledge"],
    "db": ["database"],
    "api": ["endpoint", "interface"],
    "kpi": ["metric", "indicator"],
    "crm": ["customers"],
    "vector": ["embedding", "similarity"],
    "rerank": ["reranking", "ranking"],
    "agent": ["agents", "agentic"],
    "chunk": ["chunks", "passage"],
    "pipeline": ["workflow", "orchestration"],
    "hybrid": ["fusion", "combined"],
    "crag": ["corrective", "retrieval"],
    "ppr": ["pagerank", "personalized"],
    "sse": ["streaming", "events"],
}
