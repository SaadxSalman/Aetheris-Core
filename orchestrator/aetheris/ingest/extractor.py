"""Entity & relationship extraction — LLM-backed with deterministic heuristic fallback.

Heuristic strategy (offline mode):
  * proper-noun phrase detection (capitalized runs + acronyms)
  * typed verb patterns ("X triggers Y", "X depends on Y" ...)
  * sentence-level co-occurrence edges with decayed weight
  * entity -> chunk mention index for local GraphRAG search
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field

from aetheris import llm
from aetheris.textutils import normalize_ws, sentences

_PHRASE = re.compile(
    r"\b([A-Z][A-Za-z0-9+#]*(?:\s+(?:of|the|and|for)?\s*[A-Z][A-Za-z0-9+#]*)+)\b"
    r"|\b([A-Z]{2,10}[A-Z0-9+#]*)\b"
    r"|\b([A-Z][a-z0-9+#]{2,})(?:\s+([A-Z][a-z0-9+#]{2,}))?\b"
)

_TYPED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(.{3,70}?)\s+(?:causes|triggers|induces|leads to|produces)\s+(.{3,70})", re.I), "causes"),
    (re.compile(r"(.{3,70}?)\s+(?:uses|relies on|leverages|employs|invokes)\s+(.{3,70})", re.I), "uses"),
    (re.compile(r"(.{3,70}?)\s+(?:depends on|requires|needs)\s+(.{3,70})", re.I), "depends_on"),
    (re.compile(r"(.{3,70}?)\s+(?:integrates with|connects to|works with|syncs with)\s+(.{3,70})", re.I), "integrates_with"),
    (re.compile(r"(.{3,70}?)\s+(?:stores|persists|indexes|embeds)\s+(.{3,70})", re.I), "stores"),
    (re.compile(r"(.{3,70}?)\s+(?:routes|dispatches|forwards|streams)\s+(.{3,70})", re.I), "routes"),
    (re.compile(r"(.{3,70}?)\s+(?:improves|enhances|boosts|strengthens)\s+(.{3,70})", re.I), "improves"),
    (re.compile(r"(.{3,70}?)\s+(?:prevents|mitigates|reduces|guards)\s+(.{3,70})", re.I), "mitigates"),
    (re.compile(r"(.{3,70}?)\s+(?:produces|generates|creates|extracts)\s+(.{3,70})", re.I), "produces"),
]

_TYPE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"engine|api|service|agent|gateway|server|node|worker|router|orchestrat", re.I), "component"),
    (re.compile(r"graph|index|store|database|vector|table|cache|warehouse", re.I), "datastore"),
    (re.compile(r"model|embedder|reranker|llm|encoder|decoder", re.I), "model"),
    (re.compile(r"pipeline|workflow|loop|process|strategy|method", re.I), "process"),
    (re.compile(r"document|corpus|chunk|passage|page|report", re.I), "artifact"),
    (re.compile(r"user|team|operator|admin|customer|organization", re.I), "actor"),
]

_GENERIC = {
    "the", "this", "that", "these", "those", "when", "where", "which", "what",
    "some", "any", "all", "each", "every", "its", "their", "his", "her",
    "system", "systems", "case", "way", "ways", "part", "first", "second",
    "same", "new", "way", "many", "most", "other", "more", "such", "only",
}


@dataclass
class Extraction:
    entities: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    entity_chunk: dict[str, list[str]] = field(default_factory=dict)
    method: str = "heuristic"


def normalize_entity(name: str) -> str:
    name = normalize_ws(name).strip(" .,:;\"'()[]{}")
    name = re.sub(r"\s+", " ", name)
    return name.lower()


def _infer_type(name: str) -> str:
    for pat, t in _TYPE_RULES:
        if pat.search(name):
            return t
    return "concept"


def _phrase_candidates(text: str) -> Counter:
    counts: Counter = Counter()
    for m in _PHRASE.finditer(text):
        phrase = next((g for g in m.groups() if g), None)
        if not phrase:
            continue
        words = [w for w in re.split(r"\s+", phrase.strip()) if w and w.lower() not in _GENERIC]
        if not words:
            continue
        if len(words) == 1 and len(words[0]) < 4:
            continue
        counts[" ".join(words)] += 1
        if len(words) > 1 and words[-1].lower() not in _GENERIC and len(words[-1]) > 3:
            counts[words[-1]] += 1
    return counts


def _heuristic_entities(text: str, min_mentions: int = 1) -> list[dict]:
    counts = _phrase_candidates(text)
    for m in re.finditer(r"\b([A-Z][a-z0-9+#]{2,})\b", text):
        token = m.group(1)
        if token.lower() not in _GENERIC:
            counts[token] += 1
    entities: list[dict] = []
    for name, n in counts.most_common(60):
        if n < min_mentions and len(name.split()) == 1:
            continue
        norm = normalize_entity(name)
        if not norm or norm in _GENERIC:
            continue
        entities.append({
            "id": f"ent::{norm.replace(' ', '_')}",
            "name": name,
            "normalized": norm,
            "type": _infer_type(name),
            "mentions": n,
        })
    dedup: dict[str, dict] = {}
    for ent in entities:
        prev = dedup.get(ent["normalized"])
        if prev is None or ent["mentions"] > prev["mentions"]:
            dedup[ent["normalized"]] = ent
    return sorted(dedup.values(), key=lambda e: e["mentions"], reverse=True)[:40]


def _heuristic_relationships(text: str, entity_norms: set[str]) -> list[dict]:
    rels: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def match_entity(fragment: str) -> str | None:
        frag = fragment.lower()
        best, best_len = None, 0
        for norm in entity_norms:
            if norm in frag and len(norm) > best_len:
                best, best_len = norm, len(norm)
        return best

    for sent in sentences(text):
        for pat, rtype in _TYPED_PATTERNS:
            for m in pat.finditer(sent):
                src = match_entity(m.group(1))
                dst = match_entity(m.group(2))
                if src and dst and src != dst:
                    key = (src, dst, rtype)
                    if key not in seen:
                        seen.add(key)
                        rels.append({"src_norm": src, "dst_norm": dst, "type": rtype, "weight": 1.0})
        present = [n for n in entity_norms if n in sent.lower()]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                key = (present[i], present[j], "related_to")
                rev = (present[j], present[i], "related_to")
                if key not in seen and rev not in seen:
                    seen.add(key)
                    rels.append({"src_norm": present[i], "dst_norm": present[j],
                                 "type": "related_to", "weight": 0.5})
    return rels


_LLM_PROMPT = """Extract entities and typed relationships from the text below.
Return STRICT JSON: {{"entities": [{{"name": "...", "type": "component|datastore|model|process|artifact|actor|concept"}}],
"relationships": [{{"source": "...", "target": "...", "type": "uses|depends_on|integrates_with|stores|routes|causes|produces|improves|mitigates|related_to"}}]}}
Use exact surface names. Max 30 entities, max 40 relationships. No prose.

TEXT:
{text}
"""


def _match(fragment: str, norms: set[str]) -> str | None:
    frag = fragment.lower().strip()
    if not frag:
        return None
    if frag in norms:
        return frag
    for norm in norms:
        if norm in frag or frag in norm:
            return norm
    return None


async def extract(text: str, chunks: list[dict]) -> Extraction:
    """LLM-first extraction with heuristic fallback; always builds chunk mentions."""
    entities: list[dict] = []
    relationships: list[dict] = []
    method = "heuristic"

    if llm.llm_available():
        try:
            raw = await llm.chat(
                [{"role": "user", "content": _LLM_PROMPT.format(text=text[:12000])}],
                temperature=0.0, max_tokens=2000, json_mode=True,
            )
            data = json.loads(raw)
            for e in data.get("entities", [])[:30]:
                name = str(e.get("name", "")).strip()
                if not name:
                    continue
                norm = normalize_entity(name)
                entities.append({"id": f"ent::{norm.replace(' ', '_')}", "name": name,
                                 "normalized": norm, "type": e.get("type", "concept"),
                                 "mentions": 1})
            norms = {e["normalized"] for e in entities}
            lookup = {e["name"].lower(): e["normalized"] for e in entities}
            lookup.update({e["normalized"]: e["normalized"] for e in entities})
            for r in data.get("relationships", [])[:40]:
                src = lookup.get(str(r.get("source", "")).strip().lower())
                dst = lookup.get(str(r.get("target", "")).strip().lower())
                if not src:
                    src = _match(str(r.get("source", "")), norms)
                if not dst:
                    dst = _match(str(r.get("target", "")), norms)
                if src and dst and src != dst:
                    relationships.append({"src_norm": src, "dst_norm": dst,
                                          "type": r.get("type", "related_to"), "weight": 1.0})
            if entities:
                method = "llm"
        except Exception:
            entities, relationships, method = [], [], "heuristic"

    if method == "heuristic":
        entities = _heuristic_entities(text)
        relationships = _heuristic_relationships(text, {e["normalized"] for e in entities})

    entity_chunk: dict[str, list[str]] = {e["normalized"]: [] for e in entities}
    for chunk in chunks:
        body = (chunk["text"] + " " + chunk["header_path"]).lower()
        for e in entities:
            if e["normalized"] in body:
                entity_chunk[e["normalized"]].append(chunk["id"])
    entity_chunk = {k: v for k, v in entity_chunk.items() if v}
    entities = [e for e in entities if e["normalized"] in entity_chunk]

    return Extraction(entities=entities, relationships=relationships,
                      entity_chunk=entity_chunk, method=method)


