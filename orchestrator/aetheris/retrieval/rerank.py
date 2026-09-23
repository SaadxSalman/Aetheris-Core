"""Cross-encoder reranking: Flashrank -> Cohere -> deterministic heuristic scorer."""
from __future__ import annotations

import re

import httpx

from aetheris.config import settings
from aetheris.textutils import content_tokens

_flashrank_ranker = None
_flashrank_failed = False


def _provider() -> str:
    want = settings.RERANKER_PROVIDER
    if want == "heuristic":
        return "heuristic"
    if want in ("auto", "flashrank"):
        try:
            global _flashrank_ranker, _flashrank_failed
            if _flashrank_ranker is None and not _flashrank_failed:
                from flashrank import Ranker  # type: ignore
                _flashrank_ranker = Ranker()
            if _flashrank_ranker is not None:
                return "flashrank"
        except Exception:
            _flashrank_failed = True
    if want in ("auto", "cohere") and settings.COHERE_API_KEY:
        return "cohere"
    return "heuristic"


def _heuristic_score(query: str, text: str, header: str) -> float:
    """Cross-encoder-style relevance: recall, precision, header alignment, phrase cues."""
    q = content_tokens(query)
    t = content_tokens(text)
    h = content_tokens(header)
    if not q or not t:
        return 0.0
    tset, hset = set(t), set(h)
    hits = [tok for tok in q if tok in tset or tok in hset]
    recall = len(hits) / len(q)
    precision = min(len(hits) / max(len(q), 4), 1.0)
    header_bonus = 0.15 * (len(set(q) & hset) / max(len(h), 1) if h else 0.0)
    # adjacent query-token pairs appearing together signal strong topicality
    pairs = 0
    joined = " " + " ".join(t) + " "
    for a, b in zip(q, q[1:]):
        if f" {a} {b} " in joined:
            pairs += 1
    pair_bonus = 0.1 * min(pairs / max(len(q) - 1, 1), 1.0)
    score = 0.6 * recall + 0.25 * precision + header_bonus + pair_bonus
    return max(0.0, min(1.0, score))


async def rerank(query: str, chunks: list[dict], top_k: int | None = None) -> dict:
    """Returns {provider, results:[chunk with rerank_score]} (input order preserved)."""
    top_k = top_k or settings.RERANK_TOP_K
    if not chunks:
        return {"provider": _provider(), "results": []}
    provider = _provider()

    scores: list[float] = []
    if provider == "flashrank":
        try:
            passages = [{"text": (c.get("header_path", "") + "\n" + c.get("text", ""))[:4000]}
                        for c in chunks]
            from flashrank import RerankRequest  # type: ignore
            ranked = _flashrank_ranker.rerank(RerankRequest(query=query, passages=passages))
            by_text = {p.get("text", ""): p.get("score", 0.0) for p in ranked}
            scores = [float(by_text.get((c.get("header_path", "") + "\n" + c.get("text", ""))[:4000], 0.0))
                      for c in chunks]
        except Exception:
            provider = "heuristic"
    if provider == "cohere":
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    "https://api.cohere.com/v1/rerank",
                    headers={"Authorization": f"Bearer {settings.COHERE_API_KEY}",
                             "Content-Type": "application/json"},
                    json={"model": settings.COHERE_RERANK_MODEL, "query": query,
                          "documents": [(c.get("header_path", "") + "\n" + c.get("text", ""))[:4000]
                                        for c in chunks],
                          "top_n": len(chunks)},
                )
                resp.raise_for_status()
                data = resp.json()["results"]
            scores = [0.0] * len(chunks)
            for r in data:
                scores[r["index"]] = float(r.get("relevance_score", 0.0))
        except Exception:
            provider = "heuristic"

    if provider == "heuristic" or not scores:
        provider = "heuristic"
        scores = [_heuristic_score(query, c.get("text", ""), c.get("header_path", "")) for c in chunks]

    # normalize to [0,1] across the batch for stable downstream thresholds
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    raw_map = [round(s, 4) for s in scores]
    normalized = [round((s - lo) / span, 4) if hi > lo else round(s, 4) for s in scores]

    enriched = [{**c, "rerank_score": n, "rerank_raw": r}
                for c, n, r in zip(chunks, normalized, raw_map)]
    enriched.sort(key=lambda c: c["rerank_score"], reverse=True)
    return {"provider": provider, "results": enriched[:top_k],
            "all_scores": normalized, "rejected": enriched[top_k:]}
