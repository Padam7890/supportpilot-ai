from types import SimpleNamespace
from typing import ClassVar
from uuid import uuid4

import pytest

from app.core.config import settings
from app.schemas.ai import AIExecutionOut
from app.services.ai_execution import (
    AIProviderError,
    ExecutionState,
    build_grounded_draft_graph,
    is_provider_configured,
)
from app.services.ai_worker import _safe_ai_failure_code


def test_execution_response_excludes_private_inputs_and_sensitive_provider_data():
    row = SimpleNamespace(
        id=uuid4(),
        kind="reply_draft",
        status="succeeded",
        safe_summary="Reply draft generated using 1 knowledge source(s).",
        draft="Thanks for reaching out. I can help with that.",
        citations=[],
        tool_outcomes=[{"tool": "tenant_knowledge_search", "status": "completed", "result_count": 1}],
        usage={"total_tokens": 24},
        model_name="support-model",
        error_code=None,
        created_at="2026-10-31T10:00:00Z",
        updated_at="2026-10-31T10:00:05Z",
        started_at="2026-10-31T10:00:01Z",
        completed_at="2026-10-31T10:00:05Z",
        question="private customer message",
        instructions="private agent instruction",
        integration_context_encrypted="encrypted-private-shopify-order-data",
        provider_api_key="never serialize this",
    )

    payload = AIExecutionOut.model_validate(row).model_dump()
    assert payload["draft"] == "Thanks for reaching out. I can help with that."
    assert "question" not in payload
    assert "instructions" not in payload
    assert "integration_context_encrypted" not in payload
    assert "provider_api_key" not in payload


def test_ai_execution_requires_base_url_and_model(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider_base_url", None)
    monkeypatch.setattr(settings, "ai_model", None)
    assert is_provider_configured() is False
    monkeypatch.setattr(settings, "ai_provider_base_url", "https://gateway.example/v1")
    monkeypatch.setattr(settings, "ai_model", "support-model")
    assert is_provider_configured() is True


def test_ai_failures_have_safe_actionable_codes_without_exposing_exception_text():
    provider_error = AIProviderError(
        "provider_unreachable",
        "AI provider could not be reached; token=do-not-log-this",
    )
    assert _safe_ai_failure_code(provider_error) == "provider_unreachable"
    assert _safe_ai_failure_code(RuntimeError("checkpoint connection failed")) == "ai_execution_failed"


def test_langgraph_execution_state_keeps_prompt_only_in_private_state():
    state: ExecutionState = {
        "question": "Draft a customer reply",
        "instructions": "Be concise",
        "conversation_context": [{"sender": "customer", "content": "Where is my order?"}],
        "knowledge_context": [],
    }
    assert state["question"] == "Draft a customer reply"
    assert "draft" not in state


class MockProviderResponse:
    is_error = False

    @staticmethod
    def json():
        return {
            "choices": [{"message": {"content": "Please allow thirty days for returns."}}],
            "usage": {"prompt_tokens": 17, "completion_tokens": 8, "total_tokens": 25},
        }


class MockProviderClient:
    payloads: ClassVar[list[dict]] = []

    def __init__(self, *args, **kwargs):
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json):
        self.payload = json
        type(self).payloads.append(json)
        assert url.endswith("/chat/completions")
        assert "analysis" in json["messages"][0]["content"].lower()
        assert "authorization" not in headers
        return MockProviderResponse()


@pytest.mark.anyio
async def test_langgraph_generates_bounded_customer_facing_draft(monkeypatch):
    import httpx
    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.setattr(settings, "ai_provider_base_url", "http://127.0.0.1:8012/v1")
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(settings, "ai_model", "unit-test-model")
    monkeypatch.setattr(httpx, "AsyncClient", MockProviderClient)
    graph = build_grounded_draft_graph(InMemorySaver())
    result = await graph.ainvoke(
        {
            "question": "What is the return policy?",
            "instructions": "Be concise",
            "conversation_context": [{"sender": "customer", "content": "I want to return an item."}],
            "knowledge_context": [{"document_name": "returns.txt", "chunk_index": 0, "excerpt": "Thirty day returns."}],
            "integration_context": {
                "order_number": "#1001",
                "financial_status": "PAID",
                "fulfillment_status": "FULFILLED",
            },
        },
        config={"configurable": {"thread_id": "tenant:execution"}, "recursion_limit": 5},
    )
    assert result["draft"] == "Please allow thirty days for returns."
    assert result["usage"]["total_tokens"] == 25
    assert result["model_name"] == "unit-test-model"
    payload = MockProviderClient.payloads[-1]
    assert '"order_number": "#1001"' in payload["messages"][1]["content"]
