"""Build and compile the EMR LangGraph workflow."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    generate_emr,
    load_provider_context,
    merge_context,
    retrieve_guideline_rag,
    retrieve_patient_rag,
    suggest_codes,
)
from app.graph.state import EMRGraphState

_graph: StateGraph | None = None
_compiled = None


def build_emr_graph() -> StateGraph:
    graph = StateGraph(EMRGraphState)

    # Register nodes
    graph.add_node("load_provider_context", load_provider_context)
    graph.add_node("retrieve_patient_rag", retrieve_patient_rag)
    graph.add_node("retrieve_guideline_rag", retrieve_guideline_rag)
    graph.add_node("merge_context", merge_context)
    graph.add_node("generate_emr", generate_emr)
    graph.add_node("suggest_codes", suggest_codes)

    # Edges
    graph.add_edge(START, "load_provider_context")
    graph.add_edge("load_provider_context", "retrieve_patient_rag")
    graph.add_edge("retrieve_patient_rag", "retrieve_guideline_rag")
    graph.add_edge("retrieve_guideline_rag", "merge_context")
    graph.add_edge("merge_context", "generate_emr")
    graph.add_edge("generate_emr", "suggest_codes")
    graph.add_edge("suggest_codes", END)

    return graph


def get_compiled_graph():
    """Return the cached compiled graph (lazy init)."""
    global _compiled
    if _compiled is None:
        _compiled = build_emr_graph().compile()
    return _compiled


async def run_emr_workflow(initial_state: EMRGraphState) -> EMRGraphState:
    """Execute the compiled graph and return the final state."""
    app = get_compiled_graph()
    final_state = await app.ainvoke(initial_state)
    return final_state
