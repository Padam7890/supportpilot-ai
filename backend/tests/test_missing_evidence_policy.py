"""Missing evidence must never produce invented product or policy claims."""

from app.features.ai.application.missing_evidence_policy import plan_missing_evidence_reply


def test_widget_without_evidence_escalates() -> None:
    result = plan_missing_evidence_reply(
        execution_kind="widget_reply",
        question="What is my order status?",
        intent_router_outcome={"tool": "intent_router", "status": "completed"},
    )
    assert result.reply_status == "escalated"
    assert result.outcomes[0]["tool"] == "intent_router"
    assert result.outcomes[-1]["result_count"] == 0


def test_widget_clarification_preserves_delivery_status() -> None:
    result = plan_missing_evidence_reply(
        execution_kind="widget_reply",
        question="Which one?",
        clarification="Which product do you mean?",
        delivery_status="draft_ready",
    )
    assert result.draft == "Which product do you mean?"
    assert result.reply_status == "draft_ready"


def test_playground_missing_evidence_is_deterministic() -> None:
    result = plan_missing_evidence_reply(
        execution_kind="playground", question="What is your refund policy?"
    )
    assert result.outcomes == [{
        "tool": "tenant_knowledge_search",
        "status": "completed",
        "result_count": 0,
    }]
    assert "no model answer" in result.safe_summary
