"""Structured SQL dispatch: natural-language -> guarded read-only SQLite templates."""
from __future__ import annotations

import re

from aetheris.runtime import get_runtime

_TEMPLATES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b(how many|count|number of)\b.*\b(documents?|files?|sources?)\b", re.I),
     "SELECT COUNT(*) AS documents, COUNT(DISTINCT source) AS sources FROM documents",
     "document_count"),
    (re.compile(r"\b(how many|count|number of)\b.*\b(chunks?|passages?|sections?)\b", re.I),
     "SELECT COUNT(*) AS chunks, COALESCE(SUM(token_count),0) AS tokens FROM chunks",
     "chunk_count"),
    (re.compile(r"\b(how many|count|number of)\b.*\b(entities?|nodes?)\b", re.I),
     "SELECT COUNT(*) AS entities FROM entities", "entity_count"),
    (re.compile(r"\b(how many|count|number of)\b.*\b(relationships?|edges?|links?)\b", re.I),
     "SELECT COUNT(*) AS relationships FROM relationships", "relationship_count"),
    (re.compile(r"\b(how many|count|number of)\b.*\b(communities|clusters|themes)\b", re.I),
     "SELECT COUNT(*) AS communities FROM communities", "community_count"),
    (re.compile(r"\b(list|show|which|all)\b.*\b(documents?|files?|corpus|titles?)\b", re.I),
     "SELECT title, source, uri FROM documents ORDER BY created_at DESC LIMIT 20",
     "document_list"),
    (re.compile(r"\b(list|show|distinct|which)\b.*\b(sources?|origins?)\b", re.I),
     "SELECT source, COUNT(*) AS documents FROM documents GROUP BY source ORDER BY documents DESC",
     "source_list"),
    (re.compile(r"\b(top|most|highest)\b.*\b(entit|node|concept)", re.I),
     "SELECT name, type, mentions FROM entities ORDER BY mentions DESC LIMIT 12",
     "top_entities"),
    (re.compile(r"\b(list|show|all)\b.*\b(relationships?|edges?|connections?)\b", re.I),
     "SELECT s.name AS source, d.name AS target, r.type, r.weight "
     "FROM relationships r JOIN entities s ON s.id=r.src JOIN entities d ON d.id=r.dst "
     "ORDER BY r.weight DESC LIMIT 20", "relationship_list"),
    (re.compile(r"\b(statistics|stats|overview|summary|metrics|dashboard)\b", re.I),
     "SELECT (SELECT COUNT(*) FROM documents) AS documents, "
     "(SELECT COUNT(*) FROM chunks) AS chunks, (SELECT COUNT(*) FROM entities) AS entities, "
     "(SELECT COUNT(*) FROM relationships) AS relationships, "
     "(SELECT COUNT(*) FROM communities) AS communities", "corpus_stats"),
]

SIGNAL_WORDS = re.compile(
    r"\b(how many|count|list|show|which|distinct|top|statistics|stats|overview|metrics)\b", re.I
)


def is_sql_query(query: str) -> bool:
    if not SIGNAL_WORDS.search(query):
        return False
    topics = ("document", "file", "chunk", "passage", "entit", "relationship", "edge",
              "communit", "source", "corpus", "stat", "overview", "metric")
    low = query.lower()
    return any(t in low for t in topics)


def execute(query: str) -> dict:
    """Match a natural-language aggregate/list question to a guarded template."""
    rt = get_runtime()
    for pat, sql, label in _TEMPLATES:
        if pat.search(query):
            try:
                result = rt.meta.execute_readonly(sql)
                return {"label": label, "sql": sql, "ok": True, **result}
            except Exception as exc:
                return {"label": label, "sql": sql, "ok": False, "error": str(exc),
                        "columns": [], "rows": []}
    # fallback: generic corpus stats
    sql = "SELECT COUNT(*) AS documents FROM documents"
    try:
        result = rt.meta.execute_readonly(sql)
        return {"label": "corpus_stats_fallback", "sql": sql, "ok": True, **result}
    except Exception as exc:
        return {"label": "corpus_stats_fallback", "sql": sql, "ok": False,
                "error": str(exc), "columns": [], "rows": []}


def render_markdown(result: dict) -> str:
    """Render a structured result as a markdown table for the LLM context."""
    if not result.get("ok") or not result.get("columns"):
        return ""
    cols = result["columns"]
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for row in result["rows"][:15]:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)
