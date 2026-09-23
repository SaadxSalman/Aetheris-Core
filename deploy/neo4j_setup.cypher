// ============================================================
//  Aetheris Core — Neo4j setup
//  Run in the Neo4j browser (or cypher-shell) BEFORE setting
//  GRAPH_BACKEND=neo4j (or "auto" with NEO4J_PASSWORD present).
// ============================================================

// Schema constraints / indexes
CREATE CONSTRAINT entity_normalized IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.normalized IS UNIQUE;

CREATE INDEX entity_name IF NOT EXISTS
  FOR (e:Entity) ON (e.name);

CREATE INDEX chunk_id IF NOT EXISTS
  FOR (c:Chunk) ON (c.id);

// The orchestrator writes:
//   (:Entity {normalized, name, type, mentions})
//   (:Chunk   {id, text})
//   (Entity)-[:RELATED {type, weight}]->(Entity)
//   (Entity)-[:MENTIONS_IN]->(Chunk)
//
// Optional: Graph Data Science PageRank (falls back to a
// GDS-free neighbor heuristic when the GDS plugin is absent):
//
//   CALL gds.graph.project('aetheris-graph',
//     'Entity',
//     {RELATED: {orientation: 'UNDIRECTED', properties: ['weight']}}
//   );
//
// Optional: label-propagation communities for global search:
//
//   CALL gds.lpa.stream('aetheris-graph')
//   YIELD nodeId, community;
//
// Smoke query:
MATCH (e:Entity)-[r:RELATED]->(d:Entity)
RETURN e.name, r.type, d.name, r.weight
ORDER BY r.weight DESC LIMIT 25;
