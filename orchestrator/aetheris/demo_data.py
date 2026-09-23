"""Seed corpus — ingested automatically on first boot (SEED_DEMO_CORPUS=true)."""

DEMO_DOCUMENTS: list[dict] = [
    {
        "title": "Aetheris Core — Platform Overview",
        "source": "internal-docs",
        "uri": "docs://aetheris/overview",
        "text": """# Aetheris Core Platform Overview

Aetheris Core is an autonomous multi-modal polyglot GraphRAG engine. Instead of a linear query-embed-topk-generate pipeline, it runs a stateful multi-agent orchestration graph built with LangGraph. The Intent Router Agent classifies every incoming request and dispatches it to the correct retrieval strategy: structured SQL, dense vector search, knowledge-graph traversal, or live web search.

## Orchestration Graph

The orchestration graph executes eight nodes in a conditional loop. The Intent Router Agent runs first, followed by the Hybrid Retrieval Engine, the Cross-Encoder Reranker, and the Corrective Grader Agent. When the grader rejects the retrieved context, control flows to the Query Reformulation node or the Web Fallback node before the Grounding Verification Node and the Generator are allowed to run.

The Gateway tier is a Fastify server written in TypeScript. The Gateway handles API-key enforcement, per-IP rate limiting, request identification, and Server-Sent Events fan-out toward the Next.js frontend. The Orchestrator tier is a Python FastAPI service that owns the LangGraph state machine.

## Telemetry

Every node publishes structured telemetry events over Server-Sent Events. The frontend renders these events on a React Flow canvas so operators can watch each agent transition from planning to routing to grading in real time. The engine reports route scores, per-chunk accept decisions, confidence values, and grounding audits.
""",
    },
    {
        "title": "Corrective RAG (CRAG) Design",
        "source": "internal-docs",
        "uri": "docs://aetheris/crag",
        "text": """# Corrective RAG Design

The Corrective Grader Agent implements a Corrective RAG loop. After reranking, the grader computes a confidence score from three signals: the mean raw relevance of the top chunks, token coverage of the active query, and source diversity. If confidence falls below the dynamic threshold, usually 0.42, the engine refuses to hallucinate and enters a repair cycle.

## Repair Cycle

The first repair stage rewrites the query through the Query Reformulation node. Strategies include entity focus, keyword stripping, synonym expansion, and an LLM rewrite when a language model is configured. Each reformulated query re-enters retrieval so the Hybrid Retrieval Engine can fetch a fresh candidate pool.

If every reformulation is exhausted and confidence is still low, the Corrective Grader Agent cascades to the Web Fallback node. The Web Fallback searches Tavily, SerpAPI, or DuckDuckGo, converts each result into an attributed pseudo-chunk, and merges it into the candidate pool through Reciprocal Rank Fusion.

## Grounding Verification

The Grounding Verification Node then checks whether every aspect of the question, entity seeds, keyword clusters, structured SQL rows, and live web evidence, is supported by the accepted context. When aspects are unsupported the repair loop runs again; when repairs are exhausted the engine proceeds in degraded mode and flags the answer instead of inventing facts.
""",
    },
    {
        "title": "Hybrid Retrieval and Contextual Chunk Headers",
        "source": "internal-docs",
        "uri": "docs://aetheris/retrieval",
        "text": """# Hybrid Retrieval and Contextual Chunk Headers

The Hybrid Retrieval Engine combines three retrievers. BM25 provides lexical matching over chunk text, dense vector similarity provides semantic matching through BGE-M3 or Snowflake Arctic embeddings, and graph retrieval provides Personalized PageRank traversal seeded from entities matched in the question. Results from every retriever are fused with weighted Reciprocal Rank Fusion using a rank constant of sixty.

## Contextual Chunk-Header Injector

The Contextual Chunk-Header Injector is the most important ingestion strategy. During chunking, the engine tracks the Markdown heading stack and builds a breadcrumb such as Guide > Retrieval > Fusion for every child chunk. The breadcrumb is prepended to the chunk before embedding, so the embedding of a small passage silently inherits the topic of its parent section. Citations keep the raw text, so readers never see the injected header.

The chunker splits long paragraphs at sentence boundaries with overlap, and each chunk stores a peppered SHA-256 content digest used later for cryptographic source attribution.

## Reranking

The Cross-Encoder Reranker applies Flashrank when a wheel is installed, the Cohere rerank API when a Cohere key is present, or a deterministic heuristic cross-scorer otherwise. The cross-scorer blends query-passage recall, precision, header alignment, and adjacent-token pair bonuses, and it always returns absolute relevance values that the Corrective Grader Agent can compare against a floor.
""",
    },
    {
        "title": "Storage, Security, and the Knowledge Mesh",
        "source": "internal-docs",
        "uri": "docs://aetheris/storage-security",
        "text": """# Storage, Security, and the Knowledge Mesh

Aetheris Core persists everything through a dual-layer storage architecture. SQLite is the source of truth for documents, chunks, entities, relationships, and community summaries, and it also powers the structured SQL dispatch route. The vector layer runs on Supabase pgvector through the PostgREST API when credentials are configured, otherwise on a local cosine index persisted as JSON. The knowledge graph runs on Neo4j when a password is supplied, otherwise on a NetworkX graph with greedy modularity community detection.

## Cryptographic Source Attribution

Every citation returned by the Generator carries a peppered content digest plus an HMAC-SHA256 attestation computed over the chunk identifier, the digest, and the request identifier. Clients verify a citation by posting it to the verify-citation endpoint, which recomputes the signature with a constant-time comparison. Tampering with a single byte of chunk text invalidates the attestation immediately.

## Community Summaries for Global Search

The engine recomputes graph communities after each ingestion. For global questions the Global Search path injects community summaries, generated by a language model or an extractive summarizer, as macro-thematic context blocks. For entity-centric questions the Local Search path traverses the entity subgraph around seed nodes and pulls the evidence chunks linked to each entity.

The Next.js 15 frontend uses React Flow to draw the live agent graph, Tailwind CSS for styling, and hand-built shadcn-style components for the telemetry inspector, chunk grader list, citation panel, and corpus manager.
""",
    },

]
