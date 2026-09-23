"""LangGraph agent state for the Aetheris orchestration graph."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # identity / query
    request_id: str
    query: str
    original_query: str
    active_query: str
    tried_queries: list[str]
    mode: str  # auto | local | global
    steps: int
    # routing
    route: str
    route_scores: dict[str, float]
    route_reasons: list[str]
    retrieval_plan: dict[str, bool]
    # retrieval
    candidates: list[dict]
    retrieval_counts: dict[str, int]
    structured: dict
    structured_md: str
    graph_context: dict
    web_results: list[dict]
    web_used: bool
    web_info: dict
    # loop control
    reformulation_count: int
    grounding_repairs: int
    degraded: bool
    # rerank / grade
    reranked: list[dict]
    rerank_provider: str
    rejected: list[dict]
    grade: dict
    grounding: dict
    # output
    citations: list[dict]
    answer: str
    error: str


def initial_state(query: str, request_id: str, mode: str = "auto") -> AgentState:
    return {
        "request_id": request_id,
        "query": query,
        "original_query": query,
        "active_query": query,
        "tried_queries": [],
        "mode": mode,
        "steps": 0,
        "route": "",
        "route_scores": {},
        "route_reasons": [],
        "retrieval_plan": {},
        "candidates": [],
        "retrieval_counts": {},
        "structured": {},
        "structured_md": "",
        "graph_context": {},
        "web_results": [],
        "web_used": False,
        "web_info": {},
        "reformulation_count": 0,
        "grounding_repairs": 0,
        "degraded": False,
        "reranked": [],
        "rerank_provider": "",
        "rejected": [],
        "grade": {},
        "grounding": {},
        "citations": [],
        "answer": "",
        "error": "",
    }
