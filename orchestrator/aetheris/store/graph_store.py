"""Knowledge graph backends: Neo4j | NetworkX (local) with PPR + community detection.

Dual-level GraphRAG support:
  * Local search  -> entity neighborhood subgraph + evidence chunks
  * Global search -> community detection (greedy modularity) + extractive/LLM
                     community summaries used as macro-thematic context.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import networkx as nx

from aetheris.config import settings
from aetheris.textutils import content_tokens

_PPR_CACHE: dict[str, float] = {}


def _keywords_for_texts(texts: list[str], limit: int = 8) -> list[str]:
    counts: Counter = Counter()
    for t in texts:
        counts.update(content_tokens(t))
    return [w for w, _ in counts.most_common(limit)]


class LocalGraphStore:
    backend = "local"

    def __init__(self, path: Path):
        self.path = path
        self.G = nx.Graph()
        self._entity_chunk: dict[str, list[str]] = {}
        self._chunk_text: dict[str, str] = {}
        if path.exists():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                self.G = nx.node_link_graph(blob.get("graph", {"nodes": [], "links": []}))
                self._entity_chunk = blob.get("entity_chunk", {})
                self._chunk_text = blob.get("chunk_text", {})
            except Exception:
                self.G = nx.Graph()
                self._entity_chunk, self._chunk_text = {}, {}

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({
                "graph": nx.node_link_data(self.G),
                "entity_chunk": self._entity_chunk,
                "chunk_text": self._chunk_text,
            }),
            encoding="utf-8",
        )

    # ---------------- writes ---------------- #
    def sync_document(self, doc_id: str, entities: list[dict], relationships: list[dict],
                      entity_ids: dict[str, str], entity_chunk: dict[str, list[str]],
                      chunk_text: dict[str, str]) -> None:
        """Add/refresh this document's subgraph (entity nodes keyed by normalized name)."""
        for ent in entities:
            norm = ent["normalized"]
            if self.G.has_node(norm):
                self.G.nodes[norm]["mentions"] = self.G.nodes[norm].get("mentions", 0) + ent.get("mentions", 1)
                self.G.nodes[norm]["type"] = ent.get("type", self.G.nodes[norm].get("type", "concept"))
            else:
                self.G.add_node(norm, name=ent["name"], type=ent.get("type", "concept"),
                                mentions=ent.get("mentions", 1), id=entity_ids.get(norm, norm))
        for rel in relationships:
            src, dst = rel["src_norm"], rel["dst_norm"]
            if src == dst or not self.G.has_node(src) or not self.G.has_node(dst):
                continue
            if self.G.has_edge(src, dst):
                self.G[src][dst]["weight"] += float(rel.get("weight", 1.0))
                self.G[src][dst]["types"].append(rel.get("type", "related_to"))
            else:
                self.G.add_edge(src, dst, weight=float(rel.get("weight", 1.0)),
                                types=[rel.get("type", "related_to")])
        for norm, chunks in entity_chunk.items():
            if norm in self.G:
                self._entity_chunk[norm] = sorted(set(self._entity_chunk.get(norm, [])) | set(chunks))
        self._chunk_text.update(chunk_text)
        _PPR_CACHE.clear()
        self._persist()

    def wipe(self) -> None:
        self.G.clear()
        self._entity_chunk.clear()
        self._chunk_text.clear()
        _PPR_CACHE.clear()
        self._persist()

    # ---------------- reads ---------------- #
    def find_seed_entities(self, query: str, limit: int | None = None) -> list[tuple[str, float]]:
        """Match graph nodes whose names appear in the query (longest first)."""
        q = query.lower()
        scored: list[tuple[str, float]] = []
        for node in self.G.nodes:
            name = str(self.G.nodes[node].get("name", node)).lower()
            if name in q or node in q:
                scored.append((node, 1.0 + 0.1 * len(name.split())))
                continue
            tokens = set(re.findall(r"[a-z0-9]+", name))
            q_tokens = set(re.findall(r"[a-z0-9]+", q))
            inter = tokens & q_tokens
            if tokens and inter == tokens:
                scored.append((node, 0.8))
            elif len(tokens) > 1 and len(inter) >= 2:
                scored.append((node, 0.5 * len(inter) / len(tokens)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[: (limit or settings.PPR_TOP_ENTITIES)]

    def personalized_pagerank(self, seeds: list[str], top_n: int | None = None) -> list[tuple[str, float]]:
        if not seeds or self.G.number_of_nodes() == 0:
            return []
        valid = [s for s in seeds if s in self.G]
        if not valid:
            return []
        cache_key = "|".join(sorted(valid))
        if cache_key in _PPR_CACHE:
            ranked = sorted(_PPR_CACHE.items(), key=lambda kv: kv[1], reverse=True)
            return [(n, s) for n, s in ranked if n not in valid][: top_n or settings.PPR_TOP_ENTITIES]
        personalization = {s: 1.0 for s in valid}
        try:
            pr = nx.pagerank(
                self.G,
                alpha=settings.PPR_DAMPING,
                personalization=personalization,
                weight="weight",
                max_iter=settings.PPR_ITERATIONS,
            )
        except Exception:
            return []
        for node, score in pr.items():
            _PPR_CACHE[node] = score
        ranked = sorted(pr.items(), key=lambda kv: kv[1], reverse=True)
        return [(n, s) for n, s in ranked if n not in valid][: top_n or settings.PPR_TOP_ENTITIES]

    def chunks_for_entities(self, entities: list[str], max_chunks: int = 30) -> list[str]:
        seen: list[str] = []
        for e in entities:
            for cid in self._entity_chunk.get(e, []):
                if cid not in seen:
                    seen.append(cid)
        return seen[:max_chunks]

    def subgraph_context(self, seeds: list[str], hops: int = 1) -> dict:
        if not seeds or self.G.number_of_nodes() == 0:
            return {"nodes": [], "edges": []}
        visited = set(seeds)
        frontier = list(seeds)
        for _ in range(hops):
            nxt = []
            for n in frontier:
                if not self.G.has_node(n):
                    continue
                for nb in self.G.neighbors(n):
                    if nb not in visited:
                        visited.add(nb)
                        nxt.append(nb)
            frontier = nxt
        nodes = [
            {"id": n, "name": self.G.nodes[n].get("name", n),
             "type": self.G.nodes[n].get("type", "concept"),
             "mentions": self.G.nodes[n].get("mentions", 1)}
            for n in visited if self.G.has_node(n)
        ]
        edges = []
        for u, v, data in self.G.edges(data=True):
            if u in visited and v in visited:
                edges.append({"source": u, "target": v, "weight": data.get("weight", 1.0),
                              "type": (data.get("types") or ["related_to"])[-1]})
        return {"nodes": nodes, "edges": edges}

    def communities(self) -> list[dict]:
        if self.G.number_of_nodes() < settings.COMMUNITY_MIN_SIZE:
            return []
        try:
            sets = nx.algorithms.community.greedy_modularity_communities(self.G, weight="weight")
        except Exception:
            return []
        out = []
        for i, members in enumerate(sets):
            members = sorted(members)
            if len(members) < settings.COMMUNITY_MIN_SIZE:
                continue
            texts = [self._chunk_text[c] for e in members
                     for c in self._entity_chunk.get(e, []) if c in self._chunk_text]
            out.append({
                "id": f"comm::{i}",
                "level": 0,
                "members": members,
                "keywords": _keywords_for_texts(texts)
                or [str(self.G.nodes[m].get("name", m)) for m in members[:8]],
                "_texts": texts[:6],
            })
        return out

    def stats(self) -> dict:
        return {
            "backend": "local",
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "entity_chunk_links": sum(len(v) for v in self._entity_chunk.values()),
        }

class Neo4jGraphStore:
    """Neo4j driver-backed graph (activated when GRAPH_BACKEND=auto|neo4j + creds)."""

    backend = "neo4j"

    def __init__(self) -> None:
        from neo4j import GraphDatabase  # imported lazily; package listed in requirements

        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )
        self._db = settings.NEO4J_DATABASE

    def _run(self, query: str, **params):
        with self._driver.session(database=self._db) as s:
            return list(s.run(query, **params))

    # ---------------- writes ---------------- #
    def sync_document(self, doc_id, entities, relationships, entity_ids, entity_chunk, chunk_text) -> None:
        for ent in entities:
            self._run(
                "MERGE (e:Entity {normalized:$norm}) SET e.name=$name, e.type=$type, "
                "e.mentions=coalesce(e.mentions,0)+$m",
                norm=ent["normalized"], name=ent["name"], type=ent.get("type", "concept"),
                m=int(ent.get("mentions", 1)),
            )
        for rel in relationships:
            self._run(
                "MATCH (a:Entity {normalized:$s}), (b:Entity {normalized:$d}) "
                "MERGE (a)-[r:RELATED {type:$t}]->(b) SET r.weight=coalesce(r.weight,0)+$w",
                s=rel["src_norm"], d=rel["dst_norm"], t=rel.get("type", "related_to"),
                w=float(rel.get("weight", 1.0)),
            )
        for norm, chunks in entity_chunk.items():
            for cid in chunks:
                self._run(
                    "MATCH (e:Entity {normalized:$norm}) MERGE (c:Chunk {id:$cid}) "
                    "MERGE (e)-[:MENTIONS_IN]->(c)",
                    norm=norm, cid=cid,
                )
        for cid, text in chunk_text.items():
            self._run("MERGE (c:Chunk {id:$cid}) SET c.text=$text", cid=cid, text=text)

    def wipe(self) -> None:
        self._run("MATCH (n) DETACH DELETE n")

    # ---------------- reads ---------------- #
    def find_seed_entities(self, query: str, limit: int | None = None) -> list[tuple[str, float]]:
        q = query.strip().split()[0] if query.strip() else query
        rows = self._run(
            "MATCH (e:Entity) WHERE toLower(e.name) CONTAINS toLower($q) "
            "RETURN e.normalized AS n, 1.0 AS s ORDER BY size(e.name) DESC LIMIT $lim",
            q=q, lim=limit or settings.PPR_TOP_ENTITIES,
        )
        return [(r["n"], float(r["s"])) for r in rows]

    def personalized_pagerank(self, seeds: list[str], top_n: int | None = None) -> list[tuple[str, float]]:
        """GDS-free PPR approximation: seed-mark then rank unseeded neighbors by seed mentions."""
        if not seeds:
            return []
        self._run("MATCH (e:Entity) REMOVE e.pprSeed")
        self._run("MATCH (e:Entity) WHERE e.normalized IN $seeds SET e.pprSeed=true", seeds=seeds)
        rows = self._run(
            "MATCH (e:Entity) WHERE e.pprSeed IS NULL OPTIONAL MATCH (e)<-[:RELATED]-(s:Entity) "
            "WHERE s.pprSeed IS NOT NULL RETURN e.normalized AS n, "
            "coalesce(sum(s.mentions),0.0) + 0.01 AS s ORDER BY s DESC LIMIT $lim",
            lim=top_n or settings.PPR_TOP_ENTITIES,
        )
        self._run("MATCH (e:Entity) WHERE e.pprSeed IS NOT NULL REMOVE e.pprSeed")
        return [(r["n"], float(r["s"])) for r in rows]

    def chunks_for_entities(self, entities: list[str], max_chunks: int = 30) -> list[str]:
        rows = self._run(
            "MATCH (e:Entity)-[:MENTIONS_IN]->(c:Chunk) WHERE e.normalized IN $ents "
            "RETURN DISTINCT c.id AS id LIMIT $lim",
            ents=entities, lim=max_chunks,
        )
        return [r["id"] for r in rows]

    def subgraph_context(self, seeds: list[str], hops: int = 1) -> dict:
        rows = self._run(
            "MATCH path=(a:Entity)-[:RELATED*1..2]-(b:Entity) WHERE a.normalized IN $seeds "
            "UNWIND nodes(path) AS n WITH DISTINCT n LIMIT 50 "
            "RETURN n.normalized AS id, n.name AS name, n.type AS type, n.mentions AS mentions",
            seeds=seeds,
        )
        nodes = [dict(r) for r in rows]
        ids = [n["id"] for n in nodes]
        edges = [
            dict(r) for r in self._run(
                "MATCH (a:Entity)-[r:RELATED]->(b:Entity) WHERE a.normalized IN $ids "
                "AND b.normalized IN $ids RETURN a.normalized AS source, b.normalized AS target, "
                "coalesce(r.weight,1.0) AS weight, coalesce(r.type,'related_to') AS type",
                ids=ids,
            )
        ]
        return {"nodes": nodes, "edges": edges}

    def communities(self) -> list[dict]:
        # Full label-propagation needs GDS; fall back to mention-based grouping.
        rows = self._run(
            "MATCH (e:Entity) WITH coalesce(e.community,'misc') AS comm, "
            "collect(e.normalized) AS members WHERE size(members) >= $min "
            "RETURN comm, members",
            min=settings.COMMUNITY_MIN_SIZE,
        )
        return [
            {"id": f"comm::{r['comm']}", "level": 0, "members": r["members"],
             "keywords": [m.replace("_", " ") for m in r["members"][:8]], "_texts": []}
            for r in rows
        ]

    def stats(self) -> dict:
        nodes = self._run("MATCH (n:Entity) RETURN count(n) AS c")[0]["c"]
        edges = self._run("MATCH ()-[r:RELATED]->() RETURN count(r) AS c")[0]["c"]
        return {"backend": "neo4j", "nodes": nodes, "edges": edges, "entity_chunk_links": 0}


_graph_store = None


def get_graph_store():
    """Lazy singleton honoring GRAPH_BACKEND=auto|neo4j|local."""
    global _graph_store
    if _graph_store is None:
        mode = settings.GRAPH_BACKEND
        want_neo4j = mode == "neo4j" or (mode == "auto" and settings.NEO4J_PASSWORD)
        if want_neo4j:
            try:
                store = Neo4jGraphStore()
                store.stats()  # connectivity probe
                _graph_store = store
            except Exception:
                _graph_store = LocalGraphStore(settings.DATA_DIR / "graph.json")
        else:
            _graph_store = LocalGraphStore(settings.DATA_DIR / "graph.json")
    return _graph_store




