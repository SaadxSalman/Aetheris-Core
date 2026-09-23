/* Shared types mirroring the orchestrator SSE contract. */

export type NodeStatus = "idle" | "running" | "success" | "failed";

export type AgentNodeKey =
  | "query"
  | "intent_router"
  | "web_fallback"
  | "retrieve"
  | "reformulate"
  | "rerank"
  | "grade"
  | "verify_grounding"
  | "generate"
  | "answer";

export interface UiEvent {
  type: string;
  request_id?: string;
  seq?: number;
  ts?: number;
  elapsed_ms?: number;
  node?: string;
  payload?: Record<string, unknown> & { [k: string]: any };
}

export interface Citation {
  index: number;
  chunk_id: string;
  title: string;
  header_path: string;
  source: string;
  uri: string | null;
  snippet: string;
  content_sha256: string;
  request_id: string;
  attestation: string;
  verified?: boolean;
}

export interface GradedChunk {
  chunk_id: string;
  rank?: number;
  title: string;
  header_path?: string;
  source: string;
  snippet?: string;
  rrf_score?: number;
  rerank_score?: number;
  raw?: number;
  accepted?: boolean;
  grade_reason?: string;
  retrievers?: Record<string, number>;
  retrieved: boolean;
  graded: boolean;
}

export interface NodeInfo {
  status: NodeStatus;
  badge?: string;
  detail?: string;
}

export interface RouteInfo {
  route: string;
  scores: Record<string, number>;
  reasons: string[];
  plan: Record<string, boolean>;
  seeds: string[];
}

export interface GradeInfo {
  confidence: number;
  threshold: number;
  passed: boolean;
  coverage?: number;
  diversity?: number;
  top_relevance?: number;
}

export interface GroundingInfo {
  score: number;
  threshold: number;
  passed: boolean;
  aspects: { aspect: string; kind: string; supported?: boolean }[];
  repairs: number;
  note?: string;
}

export interface FusionInfo {
  counts: Record<string, number>;
  fused: number;
  rrf_k: number;
  weights?: Record<string, number>;
}

export interface SqlInfo {
  ok: boolean;
  label: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  preview?: unknown[][];
}

export interface AnswerMeta {
  provider: string;
  degraded: boolean;
  route: string;
  confidence?: number;
  grounding_score?: number;
  web_used: boolean;
  reformulations: number;
}

export interface CorpusDoc {
  id: string;
  title: string;
  source: string;
  uri: string | null;
  sha256: string;
  created_at: number;
  chunk_count: number;
  meta: Record<string, unknown>;
}

export interface Stats {
  meta: Record<string, number>;
  vector: { backend: string; vectors: number; dim?: number; error?: string };
  graph: { backend: string; nodes: number; edges: number };
  embedder: { provider: string; model: string; dim: number };
  bm25_docs: number;
}

export interface Health {
  status: string;
  service?: string;
  app?: string;
  auth_required?: boolean;
  orchestrator?: { reachable: boolean; status?: string; version?: string };
}

export interface EngineConfig {
  app_name: string;
  env: string;
  llm_provider: string;
  llm_enabled: boolean;
  llm_model: string;
  embedder_provider: string;
  embedding_model: string;
  vector_backend: string;
  graph_backend: string;
  reranker_provider: string;
  web_provider: string;
  crag_threshold: number;
  grounding_threshold: number;
  top_k: number;
}

export interface KnowledgeGraph {
  nodes: {
    id: string;
    label: string;
    type: string;
    mentions: number;
    links: number;
  }[];
  edges: { id: string; source: string; target: string; type: string; weight: number }[];
  stats: Record<string, number | string>;
  communities: {
    id: string;
    level: number;
    size: number;
    summary: string;
    members: string[];
    keywords: string[];
  }[];
}
