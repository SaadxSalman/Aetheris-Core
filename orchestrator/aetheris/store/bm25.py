"""BM25 (Okapi) lexical index over the chunk corpus — pure Python, no deps."""
from __future__ import annotations

import math
from collections import Counter

from aetheris.textutils import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_freqs: list[Counter] = []
        self.doc_lens: list[int] = []
        self.avgdl = 0.0
        self.df: Counter = {}
        self.N = 0

    def build(self, docs: list[tuple[str, str]]) -> None:
        """docs: [(chunk_id, text)]"""
        self.doc_ids = [d[0] for d in docs]
        self.doc_freqs = [Counter(tokenize(d[1])) for d in docs]
        self.doc_lens = [sum(c.values()) for c in self.doc_freqs]
        self.N = len(docs)
        self.avgdl = (sum(self.doc_lens) / self.N) if self.N else 0.0
        self.df = Counter()
        for freq in self.doc_freqs:
            for term in freq:
                self.df[term] += 1

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        if self.N == 0:
            return []
        q_terms = tokenize(query)
        scores: dict[str, float] = {}
        for term in q_terms:
            n_q = self.df.get(term, 0)
            if not n_q:
                continue
            idf = math.log(1 + (self.N - n_q + 0.5) / (n_q + 0.5))
            for i, freq in enumerate(self.doc_freqs):
                f = freq.get(term, 0)
                if not f:
                    continue
                dl = self.doc_lens[i]
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                scores[self.doc_ids[i]] = scores.get(self.doc_ids[i], 0.0) + idf * f * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:top_k]
