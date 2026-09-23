"""Configuration loader — reads the single root .env shared by the whole stack."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../Aetheris-Core
load_dotenv(REPO_ROOT / ".env", override=False)


def _s(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _i(name: str, default: int) -> int:
    try:
        return int(float(_s(name, str(default))))
    except ValueError:
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(_s(name, str(default)))
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    raw = _s(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in _s(name, default).split(",") if x.strip()]


@dataclass(slots=True)
class Settings:
    # ---- app / runtime ----
    APP_NAME: str = "Aetheris Core"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_LOG_LEVEL: str = "INFO"
    DATA_DIR: Path = REPO_ROOT / ".data"
    # ---- network ----
    ORCHESTRATOR_HOST: str = "127.0.0.1"
    ORCHESTRATOR_PORT: int = 8000
    GATEWAY_HOST: str = "127.0.0.1"
    GATEWAY_PORT: int = 4000
    FRONTEND_PORT: int = 3000
    PUBLIC_API_BASE_URL: str = "http://localhost:4000"
    ORCHESTRATOR_URL: str = "http://127.0.0.1:8000"
    CORS_ORIGINS: list[str] = field(default_factory=list)
    # ---- security ----
    GATEWAY_API_KEY: str = ""
    GATEWAY_REQUIRE_AUTH: bool = False
    ATTRIBUTION_HMAC_SECRET: str = "aeth-attr-dev-secret"
    CONTENT_HASH_PEPPER: str = "aeth-pepper-dev"
    GATEWAY_RATE_LIMIT_PER_MIN: int = 120
    # ---- LLM ----
    LLM_PROVIDER: str = "none"          # openai | groq | ollama | none
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 1400
    LLM_TIMEOUT_SECONDS: int = 90
    LLM_MAX_RETRIES: int = 2
    # ---- embeddings ----
    EMBEDDER_PROVIDER: str = "local"     # local | openai_compatible
    EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 384
    EMBEDDING_AUTO_DIM: bool = True
    # ---- vector backend ----
    VECTOR_BACKEND: str = "auto"         # auto | supabase | local
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SCHEMA: str = "public"
    SUPABASE_VECTOR_TABLE: str = "aetheris_chunks"
    SUPABASE_MATCH_RPC: str = "match_aetheris_chunks"
    # ---- graph backend ----
    GRAPH_BACKEND: str = "auto"          # auto | neo4j | local
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"
    # ---- retrieval ----
    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_CANDIDATE_POOL: int = 60
    RRF_K: int = 60
    W_BM25: float = 1.0
    W_DENSE: float = 1.0
    W_GRAPH: float = 0.85
    PPR_ITERATIONS: int = 30
    PPR_DAMPING: float = 0.85
    PPR_TOP_ENTITIES: int = 6
    COMMUNITY_MIN_SIZE: int = 3
    COMMUNITY_MAX_LEVELS: int = 2
    # ---- reranker ----
    RERANKER_PROVIDER: str = "auto"      # auto | flashrank | cohere | heuristic
    COHERE_API_KEY: str = ""
    COHERE_RERANK_MODEL: str = "rerank-english-v3.0"
    RERANK_TOP_K: int = 6
    # ---- CRAG ----
    CRAG_CONFIDENCE_THRESHOLD: float = 0.42
    CRAG_MAX_REFORMULATIONS: int = 2
    CRAG_ENABLE_WEB_FALLBACK: bool = True
    GROUNDING_MIN_SCORE: float = 0.55
    GROUNDING_MAX_REPAIRS: int = 1
    # ---- web search ----
    WEB_SEARCH_PROVIDER: str = "auto"    # auto | tavily | serpapi | duckduckgo
    TAVILY_API_KEY: str = ""
    SERPAPI_API_KEY: str = ""
    WEB_RESULT_COUNT: int = 5
    WEB_TIMEOUT_SECONDS: int = 12
    # ---- ingestion ----
    CHUNK_SIZE: int = 700
    CHUNK_OVERLAP: int = 140
    CHUNK_HEADER_MAX_LEVELS: int = 4
    SEED_DEMO_CORPUS: bool = True
    # ---- telemetry ----
    SSE_HEARTBEAT_SECONDS: int = 10
    TELEMETRY_MAX_EVENTS: int = 600
    TELEMETRY_INCLUDE_CHUNKS: bool = True


    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(_s("DATA_DIR", ".data"))
        if not data_dir.is_absolute():
            data_dir = REPO_ROOT / data_dir
        s = cls(
            APP_NAME=_s("APP_NAME", "Aetheris Core"),
            APP_ENV=_s("APP_ENV", "development"),
            APP_DEBUG=_b("APP_DEBUG", True),
            APP_LOG_LEVEL=_s("APP_LOG_LEVEL", "INFO"),
            DATA_DIR=data_dir,
            ORCHESTRATOR_HOST=_s("ORCHESTRATOR_HOST", "127.0.0.1"),
            ORCHESTRATOR_PORT=_i("ORCHESTRATOR_PORT", 8000),
            GATEWAY_HOST=_s("GATEWAY_HOST", "127.0.0.1"),
            GATEWAY_PORT=_i("GATEWAY_PORT", 4000),
            FRONTEND_PORT=_i("FRONTEND_PORT", 3000),
            PUBLIC_API_BASE_URL=_s("PUBLIC_API_BASE_URL", "http://localhost:4000"),
            ORCHESTRATOR_URL=_s("ORCHESTRATOR_URL", "http://127.0.0.1:8000"),
            CORS_ORIGINS=_csv("CORS_ORIGINS", "http://localhost:3000"),
            GATEWAY_API_KEY=_s("GATEWAY_API_KEY"),
            GATEWAY_REQUIRE_AUTH=_b("GATEWAY_REQUIRE_AUTH", False),
            ATTRIBUTION_HMAC_SECRET=_s("ATTRIBUTION_HMAC_SECRET", "aeth-attr-dev-secret"),
            CONTENT_HASH_PEPPER=_s("CONTENT_HASH_PEPPER", "aeth-pepper-dev"),
            GATEWAY_RATE_LIMIT_PER_MIN=_i("GATEWAY_RATE_LIMIT_PER_MIN", 120),
            LLM_PROVIDER=_s("LLM_PROVIDER", "none").lower(),
            OPENAI_API_KEY=_s("OPENAI_API_KEY"),
            OPENAI_BASE_URL=_s("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            LLM_MODEL=_s("LLM_MODEL", "gpt-4o-mini"),
            GROQ_API_KEY=_s("GROQ_API_KEY"),
            GROQ_BASE_URL=_s("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            OLLAMA_BASE_URL=_s("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            LLM_TEMPERATURE=_f("LLM_TEMPERATURE", 0.2),
            LLM_MAX_TOKENS=_i("LLM_MAX_TOKENS", 1400),
            LLM_TIMEOUT_SECONDS=_i("LLM_TIMEOUT_SECONDS", 90),
            LLM_MAX_RETRIES=_i("LLM_MAX_RETRIES", 2),
            EMBEDDER_PROVIDER=_s("EMBEDDER_PROVIDER", "local").lower(),
            EMBEDDING_BASE_URL=_s("EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
            EMBEDDING_API_KEY=_s("EMBEDDING_API_KEY"),
            EMBEDDING_MODEL=_s("EMBEDDING_MODEL", "bge-m3"),
            EMBEDDING_DIM=_i("EMBEDDING_DIM", 384),
            EMBEDDING_AUTO_DIM=_b("EMBEDDING_AUTO_DIM", True),
            VECTOR_BACKEND=_s("VECTOR_BACKEND", "auto").lower(),
            SUPABASE_URL=_s("SUPABASE_URL"),
            SUPABASE_SERVICE_ROLE_KEY=_s("SUPABASE_SERVICE_ROLE_KEY"),
            SUPABASE_ANON_KEY=_s("SUPABASE_ANON_KEY"),
            SUPABASE_SCHEMA=_s("SUPABASE_SCHEMA", "public"),
            SUPABASE_VECTOR_TABLE=_s("SUPABASE_VECTOR_TABLE", "aetheris_chunks"),
            SUPABASE_MATCH_RPC=_s("SUPABASE_MATCH_RPC", "match_aetheris_chunks"),
            GRAPH_BACKEND=_s("GRAPH_BACKEND", "auto").lower(),
            NEO4J_URI=_s("NEO4J_URI", "bolt://localhost:7687"),
            NEO4J_USERNAME=_s("NEO4J_USERNAME", "neo4j"),
            NEO4J_PASSWORD=_s("NEO4J_PASSWORD"),
            NEO4J_DATABASE=_s("NEO4J_DATABASE", "neo4j"),
            RETRIEVAL_TOP_K=_i("RETRIEVAL_TOP_K", 8),
            RETRIEVAL_CANDIDATE_POOL=_i("RETRIEVAL_CANDIDATE_POOL", 60),
            RRF_K=_i("RRF_K", 60),
            W_BM25=_f("W_BM25", 1.0),
            W_DENSE=_f("W_DENSE", 1.0),
            W_GRAPH=_f("W_GRAPH", 0.85),
            PPR_ITERATIONS=_i("PPR_ITERATIONS", 30),
            PPR_DAMPING=_f("PPR_DAMPING", 0.85),
            PPR_TOP_ENTITIES=_i("PPR_TOP_ENTITIES", 6),
            COMMUNITY_MIN_SIZE=_i("COMMUNITY_MIN_SIZE", 3),
            COMMUNITY_MAX_LEVELS=_i("COMMUNITY_MAX_LEVELS", 2),
            RERANKER_PROVIDER=_s("RERANKER_PROVIDER", "auto").lower(),
            COHERE_API_KEY=_s("COHERE_API_KEY"),
            COHERE_RERANK_MODEL=_s("COHERE_RERANK_MODEL", "rerank-english-v3.0"),
            RERANK_TOP_K=_i("RERANK_TOP_K", 6),
            CRAG_CONFIDENCE_THRESHOLD=_f("CRAG_CONFIDENCE_THRESHOLD", 0.42),
            CRAG_MAX_REFORMULATIONS=_i("CRAG_MAX_REFORMULATIONS", 2),
            CRAG_ENABLE_WEB_FALLBACK=_b("CRAG_ENABLE_WEB_FALLBACK", True),
            GROUNDING_MIN_SCORE=_f("GROUNDING_MIN_SCORE", 0.55),
            GROUNDING_MAX_REPAIRS=_i("GROUNDING_MAX_REPAIRS", 1),
            WEB_SEARCH_PROVIDER=_s("WEB_SEARCH_PROVIDER", "auto").lower(),
            TAVILY_API_KEY=_s("TAVILY_API_KEY"),
            SERPAPI_API_KEY=_s("SERPAPI_API_KEY"),
            WEB_RESULT_COUNT=_i("WEB_RESULT_COUNT", 5),
            WEB_TIMEOUT_SECONDS=_i("WEB_TIMEOUT_SECONDS", 12),
            CHUNK_SIZE=_i("CHUNK_SIZE", 700),
            CHUNK_OVERLAP=_i("CHUNK_OVERLAP", 140),
            CHUNK_HEADER_MAX_LEVELS=_i("CHUNK_HEADER_MAX_LEVELS", 4),
            SEED_DEMO_CORPUS=_b("SEED_DEMO_CORPUS", True),
            SSE_HEARTBEAT_SECONDS=_i("SSE_HEARTBEAT_SECONDS", 10),
            TELEMETRY_MAX_EVENTS=_i("TELEMETRY_MAX_EVENTS", 600),
            TELEMETRY_INCLUDE_CHUNKS=_b("TELEMETRY_INCLUDE_CHUNKS", True),
        )
        s.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return s


settings = Settings.from_env()


def _vector_backend_label() -> str:
    if settings.VECTOR_BACKEND != "auto":
        return settings.VECTOR_BACKEND
    return "supabase" if (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY) else "local"


def public_config() -> dict:
    """Non-secret runtime configuration surfaced to the frontend."""
    return {
        "app_name": settings.APP_NAME,
        "env": settings.APP_ENV,
        "llm_provider": settings.LLM_PROVIDER if settings.LLM_PROVIDER != "none" else "extractive-fallback",
        "llm_enabled": settings.LLM_PROVIDER != "none" and bool(
            settings.OPENAI_API_KEY or settings.GROQ_API_KEY or settings.LLM_PROVIDER == "ollama"
        ),
        "llm_model": settings.LLM_MODEL,
        "embedder_provider": settings.EMBEDDER_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL if settings.EMBEDDER_PROVIDER != "local" else "local-hash-384",
        "vector_backend": _vector_backend_label(),
        "graph_backend": settings.GRAPH_BACKEND,
        "reranker_provider": settings.RERANKER_PROVIDER,
        "web_provider": settings.WEB_SEARCH_PROVIDER,
        "crag_threshold": settings.CRAG_CONFIDENCE_THRESHOLD,
        "grounding_threshold": settings.GROUNDING_MIN_SCORE,
        "top_k": settings.RETRIEVAL_TOP_K,
        "require_auth": settings.GATEWAY_REQUIRE_AUTH,
        "gateway_api_key": settings.GATEWAY_API_KEY,
    }


