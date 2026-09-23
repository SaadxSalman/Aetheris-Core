"""SQLite source-of-truth store: documents, chunks, entities, relations, communities.

Also powers the structured-SQL dispatch route of the intent router.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual',
    uri TEXT, sha256 TEXT NOT NULL, created_at REAL NOT NULL, meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL, header_path TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL, embedded_text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0, content_sha256 TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, normalized TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL DEFAULT 'concept', mentions INTEGER NOT NULL DEFAULT 1, doc_id TEXT
);
CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY, src TEXT NOT NULL, dst TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'related_to', weight REAL NOT NULL DEFAULT 1.0,
    evidence_chunk TEXT, doc_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_rel_src ON relationships(src);
CREATE TABLE IF NOT EXISTS entity_chunks (
    entity_id TEXT NOT NULL, chunk_id TEXT NOT NULL, PRIMARY KEY (entity_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS communities (
    id TEXT PRIMARY KEY, level INTEGER NOT NULL DEFAULT 0, members_json TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
    keywords_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL
);
"""

ALLOWED_TABLES = {"documents", "chunks", "entities", "relationships", "entity_chunks", "communities"}


class MetaStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(DDL)
            self._conn.commit()

    # ---------------- documents / chunks ---------------- #
    def upsert_document(self, doc_id: str, title: str, source: str, uri: str | None,
                        sha256: str, meta: dict | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents(id,title,source,uri,sha256,created_at,meta_json) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, source=excluded.source, "
                "uri=excluded.uri, sha256=excluded.sha256, meta_json=excluded.meta_json",
                (doc_id, title, source, uri, sha256, time.time(), json.dumps(meta or {})),
            )
            self._conn.commit()

    def replace_chunks(self, doc_id: str, chunks: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            self._conn.executemany(
                "INSERT INTO chunks(id,doc_id,ordinal,header_path,text,embedded_text,"
                "token_count,content_sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                [
                    (c["id"], doc_id, c["ordinal"], c["header_path"], c["text"],
                     c["embedded_text"], c["token_count"], c["content_sha256"], time.time())
                    for c in chunks
                ],
            )
            self._conn.execute("DELETE FROM entity_chunks WHERE chunk_id NOT IN (SELECT id FROM chunks)")
            self._conn.commit()

    def get_chunk(self, chunk_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT c.*, d.title AS doc_title, d.source AS doc_source, d.uri AS doc_uri "
                "FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id=?",
                (chunk_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_chunks_for_doc(self, doc_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (doc_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def all_chunks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.id, c.doc_id, c.ordinal, c.header_path, c.text, c.embedded_text, "
                "c.token_count, d.title AS doc_title, d.source AS doc_source, d.uri AS doc_uri "
                "FROM chunks c JOIN documents d ON d.id=c.doc_id ORDER BY c.created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_documents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM documents d "
                "LEFT JOIN chunks c ON c.doc_id=d.id GROUP BY d.id ORDER BY d.created_at DESC"
            ).fetchall()
        return [
            {**{k: r[k] for k in r.keys() if k != "meta_json"},
             "meta": json.loads(r["meta_json"] or "{}")}
            for r in rows
        ]

    def delete_document(self, doc_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM entity_chunks WHERE chunk_id IN (SELECT id FROM chunks WHERE doc_id=?)",
                (doc_id,),
            )
            self._conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            self._conn.execute("DELETE FROM relationships WHERE doc_id=?", (doc_id,))
            self._conn.execute("DELETE FROM entities WHERE doc_id=?", (doc_id,))
            self._conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
            self._conn.commit()

    def wipe(self) -> None:
        with self._lock:
            for t in ("entity_chunks", "chunks", "relationships", "entities", "communities", "documents"):
                self._conn.execute(f"DELETE FROM {t}")
            self._conn.commit()

    # ---------------- entities / relations ---------------- #
    def upsert_entities(self, doc_id: str, entities: list[dict]) -> dict[str, str]:
        """Returns mapping normalized-name -> entity id."""
        mapping: dict[str, str] = {}
        with self._lock:
            for ent in entities:
                norm = ent["normalized"]
                row = self._conn.execute(
                    "SELECT id, mentions FROM entities WHERE normalized=?", (norm,)
                ).fetchone()
                if row:
                    eid = row["id"]
                    self._conn.execute(
                        "UPDATE entities SET mentions=mentions+?, type=?, doc_id=? WHERE id=?",
                        (int(ent.get("mentions", 1)), ent.get("type", "concept"), doc_id, eid),
                    )
                else:
                    eid = ent["id"]
                    self._conn.execute(
                        "INSERT INTO entities(id,name,normalized,type,mentions,doc_id) VALUES(?,?,?,?,?,?)",
                        (eid, ent["name"], norm, ent.get("type", "concept"),
                         int(ent.get("mentions", 1)), doc_id),
                    )
                mapping[norm] = eid
            self._conn.commit()
        return mapping

    def link_entity_chunks(self, links: list[tuple[str, str]]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO entity_chunks(entity_id, chunk_id) VALUES(?,?)", links
            )
            self._conn.commit()

    def upsert_relationships(self, doc_id: str, rels: list[dict], entity_ids: dict[str, str],
                             chunk_ids_by_norm: dict[str, list[str]] | None = None) -> int:
        count = 0
        with self._lock:
            for rel in rels:
                src = entity_ids.get(rel["src_norm"])
                dst = entity_ids.get(rel["dst_norm"])
                if not src or not dst or src == dst:
                    continue
                rid = f"rel::{src}::{dst}::{rel['type']}"
                evidence = None
                if chunk_ids_by_norm:
                    shared = set(chunk_ids_by_norm.get(rel["src_norm"], [])) & set(
                        chunk_ids_by_norm.get(rel["dst_norm"], [])
                    )
                    evidence = sorted(shared)[0] if shared else None
                self._conn.execute(
                    "INSERT INTO relationships(id,src,dst,type,weight,evidence_chunk,doc_id) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "weight=relationships.weight+excluded.weight",
                    (rid, src, dst, rel.get("type", "related_to"),
                     float(rel.get("weight", 1.0)), evidence, doc_id),
                )
                count += 1
            self._conn.commit()
        return count

    def all_entities(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT e.*, COUNT(ec.chunk_id) AS chunk_links FROM entities e "
                "LEFT JOIN entity_chunks ec ON ec.entity_id=e.id GROUP BY e.id"
            ).fetchall()
        return [dict(r) for r in rows]

    def entity_chunk_map(self) -> dict[str, list[str]]:
        with self._lock:
            rows = self._conn.execute("SELECT entity_id, chunk_id FROM entity_chunks").fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["entity_id"], []).append(r["chunk_id"])
        return out

    def all_relationships(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM relationships").fetchall()
        return [dict(r) for r in rows]

    # ---------------- communities ---------------- #
    def replace_communities(self, communities: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM communities")
            self._conn.executemany(
                "INSERT INTO communities(id,level,members_json,size,summary,keywords_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                [
                    (c["id"], c.get("level", 0), json.dumps(c["members"]), len(c["members"]),
                     c.get("summary", ""), json.dumps(c.get("keywords", [])), time.time())
                    for c in communities
                ],
            )
            self._conn.commit()

    def all_communities(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM communities ORDER BY size DESC").fetchall()
        return [
            {**{k: r[k] for k in ("id", "level", "size", "summary")},
             "members": json.loads(r["members_json"]),
             "keywords": json.loads(r["keywords_json"] or "[]")}
            for r in rows
        ]

    # ---------------- stats / structured SQL ---------------- #
    def stats(self) -> dict:
        with self._lock:
            def q(sql: str):
                return self._conn.execute(sql).fetchone()[0]

            return {
                "documents": q("SELECT COUNT(*) FROM documents"),
                "chunks": q("SELECT COUNT(*) FROM chunks"),
                "entities": q("SELECT COUNT(*) FROM entities"),
                "relationships": q("SELECT COUNT(*) FROM relationships"),
                "communities": q("SELECT COUNT(*) FROM communities"),
                "entity_chunk_links": q("SELECT COUNT(*) FROM entity_chunks"),
                "sources": q("SELECT COUNT(DISTINCT source) FROM documents"),
            }

    def execute_readonly(self, sql: str, params: tuple = ()) -> dict:
        """Guarded read-only executor used by the structured SQL dispatch route."""
        cleaned = sql.strip().rstrip(";")
        if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            raise ValueError("Only SELECT queries are permitted")
        if ";" in cleaned:
            raise ValueError("Multiple statements are not permitted")
        tables = set(re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned, re.IGNORECASE))
        illegal = {t for t in tables if t.lower() not in ALLOWED_TABLES}
        if illegal:
            raise ValueError(f"Unknown table(s): {', '.join(sorted(illegal))}")
        with self._lock:
            cur = self._conn.execute(cleaned, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        return {"columns": cols, "rows": [list(r) for r in rows[:50]]}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def db_path_for(data_dir: Path) -> Path:
    return data_dir / "aetheris.db"


