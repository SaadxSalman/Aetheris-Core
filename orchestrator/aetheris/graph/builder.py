"""LangGraph wiring: StateGraph, nodes, conditional CRAG/grounding loops."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from aetheris.graph.nodes import (
    generate,
    grade,
    intent_router,
    retrieve,
    reformulate,
    rerank_node,
    verify_grounding,
    web_fallback,
)
from aetheris.graph.state import AgentState


def _after_router(state: AgentState) -> str:
    if state.get("route") == "web" and not state.get("web_used"):
        return "web"
    return "retrieve"


def _after_grade(state: AgentState) -> str:
    grade_info = state.get("grade", {})
    if grade_info.get("passed"):
        return "grounding"
    if state.get("steps", 0) > 20:
        return "grounding"
    if state.get("reformulation_count", 0) < _max_rewrites():
        return "reformulate"
    if _web_enabled() and not state.get("web_used"):
        return "web"
    return "grounding"


def _after_grounding(state: AgentState) -> str:
    g = state.get("grounding", {})
    if g.get("passed"):
        return "generate"
    if state.get("steps", 0) > 20:
        return "generate"
    if state.get("grounding_repairs", 0) < _max_repairs():
        return "reformulate"
    return "generate"


def _max_rewrites() -> int:
    from aetheris.config import settings
    return settings.CRAG_MAX_REFORMULATIONS


def _max_repairs() -> int:
    from aetheris.config import settings
    return settings.GROUNDING_MAX_REPAIRS


def _web_enabled() -> bool:
    from aetheris.config import settings
    return bool(settings.CRAG_ENABLE_WEB_FALLBACK)


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("intent_router", intent_router)
    g.add_node("web_fallback", web_fallback)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank_node)
    g.add_node("grade", grade)
    g.add_node("reformulate", reformulate)
    g.add_node("verify_grounding", verify_grounding)
    g.add_node("generate", generate)

    g.add_edge(START, "intent_router")
    g.add_conditional_edges("intent_router", _after_router,
                            {"web": "web_fallback", "retrieve": "retrieve"})
    g.add_edge("web_fallback", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "grade")
    g.add_conditional_edges(
        "grade", _after_grade,
        {"reformulate": "reformulate", "web": "web_fallback",
         "grounding": "verify_grounding", "generate": "generate"},
    )
    g.add_edge("reformulate", "retrieve")
    g.add_conditional_edges(
        "verify_grounding", _after_grounding,
        {"reformulate": "reformulate", "generate": "generate"},
    )
    g.add_edge("generate", END)
    return g.compile()


graph = None


def get_graph():
    global graph
    if graph is None:
        graph = build_graph()
    return graph
