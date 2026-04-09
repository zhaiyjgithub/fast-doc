"""Tests for LangGraph workflow skeleton."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.workflow import build_emr_graph, run_emr_workflow

_MOCK_SOAP = json.dumps({
    "subjective": "Cough and dyspnea",
    "objective": "SpO2 93%",
    "assessment": "COPD exacerbation",
    "plan": "Prednisone",
})


def test_graph_compiles():
    """Graph must compile without errors."""
    graph = build_emr_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_graph_node_names():
    """All required nodes must be present."""
    graph = build_emr_graph()
    node_names = set(graph.nodes.keys())
    required = {
        "load_provider_context",
        "retrieve_patient_rag",
        "retrieve_guideline_rag",
        "merge_context",
        "generate_emr",
        "suggest_codes",
    }
    assert required.issubset(node_names)


async def test_workflow_runs_end_to_end():
    """Workflow must complete without raising exceptions (LLM mocked)."""
    initial_state = {
        "request_id": "test-req-001",
        "encounter_id": "enc-001",
        "patient_id": "pat-001",
        "transcript": "Patient presents with shortness of breath and productive cough.",
        "provider_prompt_style": "standard",
    }
    with patch(
        "app.graph.nodes.llm_adapter.chat",
        new_callable=AsyncMock,
        return_value=_MOCK_SOAP,
    ):
        result = await run_emr_workflow(initial_state)

    assert result["current_node"] == "suggest_codes"
    assert "patient_chunks" in result
    assert "guideline_chunks" in result
    assert "merged_context" in result
    assert "emr_text" in result
    assert "icd_suggestions" in result
    assert "cpt_suggestions" in result


async def test_workflow_preserves_input_fields():
    """Input fields must survive through the graph unchanged."""
    initial_state = {
        "request_id": "req-preserve",
        "encounter_id": "enc-xyz",
        "transcript": "Chronic cough x 3 months",
        "provider_prompt_style": "concise",
    }
    with patch(
        "app.graph.nodes.llm_adapter.chat",
        new_callable=AsyncMock,
        return_value=_MOCK_SOAP,
    ):
        result = await run_emr_workflow(initial_state)

    assert result["request_id"] == "req-preserve"
    assert result["transcript"] == "Chronic cough x 3 months"
