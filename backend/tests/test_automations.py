from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.features.automations.router import _workflow_out_or_skip_invalid
from app.features.automations.contracts import (
    WorkflowCanvasLayout,
    WorkflowCreate,
    WorkflowDefinition,
    default_canvas_layout,
)
from app.models import AutomationWorkflow
from app.features.automations.policy import (
    EvaluationContext,
    evaluate_conditions,
    preview_definition,
)
from app.workers.handlers.automation import retry_delay_seconds


def _ctx(*, message: str, priority: str = "normal", status: str = "open", channel: str = "web", first: bool = True):
    return EvaluationContext(
        message=message,
        ticket_priority=priority,
        ticket_status=status,
        channel=channel,
        is_first_customer_message=first,
        assignee_present=False,
        conversation_ai_mode="human",
        shopify_connected=False,
        trigger_ai_agent_id=None,
        trigger_integration_connection_id=None,
        conversation_ai_agent_id=None,
        conversation_integration_connection_id=None,
    )


@pytest.mark.parametrize(
    ("message", "conditions", "expected"),
    [
        ("Where is my order?", [], True),
        ("I need to cancel this", [{"kind": "contains_keyword", "value": "cancel"}], True),
        ("Please refund me", [{"kind": "contains_keyword", "value": "CANCEL"}], False),
        (
            "Cancel my order please",
            [
                {"kind": "contains_keyword", "value": "cancel"},
                {"kind": "contains_keyword", "value": "order"},
            ],
            True,
        ),
    ],
)
def test_automation_conditions_are_deterministic(message, conditions, expected):
    definition = WorkflowDefinition.model_validate({
        "trigger": "customer_message_received",
        "conditions": conditions,
        "actions": [{"kind": "set_priority", "value": "high"}],
    })
    assert evaluate_conditions(definition, _ctx(message=message)) is expected


def test_automation_preview_reports_matching_conditions_and_actions_without_side_effects():
    definition = WorkflowDefinition.model_validate({
        "trigger": "customer_message_received",
        "conditions": [
            {"kind": "contains_keyword", "value": "refund"},
            {"kind": "contains_keyword", "value": "order"},
        ],
        "actions": [{"kind": "set_priority", "value": "urgent"}],
    })

    matched = preview_definition(definition, message="Please help with my REFUND order")
    already_urgent = preview_definition(
        definition,
        message="Please help with my REFUND order",
        current_ticket_priority="urgent",
    )
    missed = preview_definition(definition, message="Where is my package?")

    assert matched.matches is True
    assert [c.matched for c in matched.conditions] == [True, True]
    assert matched.planned_actions[0].summary == "Set ticket priority to urgent"
    assert already_urgent.planned_actions[0].summary == "No change: ticket is already urgent priority"
    assert missed.matches is False
    assert [c.matched for c in missed.conditions] == [False, False]
    assert missed.planned_actions == []


def test_workflow_rejects_untrusted_or_unsupported_action_shapes():
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({
            "trigger": "customer_message_received",
            "actions": [{"kind": "run_sql", "query": "DELETE FROM tickets"}],
        })
    with pytest.raises(ValidationError):
        WorkflowDefinition.model_validate({
            "trigger": "webhook_received",
            "actions": [{"kind": "set_priority", "value": "urgent"}],
        })


def test_workflow_assignment_action_is_typed_and_tenant_target_is_uuid():
    user_id = uuid4()
    definition = WorkflowDefinition.model_validate({
        "trigger": "customer_message_received",
        "actions": [{"kind": "assign_to_user", "user_id": str(user_id)}],
    })
    assert definition.actions[0].user_id == user_id


def test_default_canvas_layout_has_ordered_positions():
    layout = default_canvas_layout(3, 2)

    assert [position.y for position in layout.conditions] == [154, 286, 418]
    assert [position.y for position in layout.actions] == [576, 708]
    assert layout.trigger.y < layout.conditions[0].y < layout.actions[0].y


def test_workflow_rejects_canvas_layout_with_missing_condition_position():
    with pytest.raises(ValidationError, match="one position for each condition"):
        WorkflowCreate.model_validate({
            "name": "Route refund request",
            "definition": {
                "trigger": "customer_message_received",
                "conditions": [{"kind": "contains_keyword", "value": "refund"}],
                "actions": [{"kind": "set_priority", "value": "high"}],
            },
            "canvas_layout": {
                "trigger": {"x": 100, "y": 20},
                "conditions": [],
                "actions": [{"x": 100, "y": 300}],
            },
        })


def test_canvas_positions_are_bounded_and_strict():
    with pytest.raises(ValidationError):
        WorkflowCanvasLayout.model_validate({
            "trigger": {"x": 1201, "y": 20},
            "conditions": [],
            "actions": [{"x": 100, "y": 300}],
        })


@pytest.mark.parametrize("attempt", [1, 2, 3, 8, 30])
def test_automation_retry_delay_is_bounded_and_jittered(attempt):
    assert retry_delay_seconds(attempt, random_value=0.5) >= 1
    assert retry_delay_seconds(attempt, random_value=1.0) <= 300
    assert retry_delay_seconds(attempt, random_value=0.0) == 1


def test_list_skip_returns_none_for_invalid_stored_definition():
    org_id = uuid4()
    user_id = uuid4()
    broken = AutomationWorkflow(
        organization_id=org_id,
        name="Broken legacy",
        status="draft",
        draft_version=1,
        draft_definition={
            "trigger": "customer_message_received",
            "actions": [{"kind": "run_sql", "query": "DELETE FROM tickets"}],
        },
        created_by_user_id=user_id,
    )
    broken.id = uuid4()

    assert _workflow_out_or_skip_invalid(broken) is None


def test_list_skip_returns_output_for_valid_stored_definition():
    org_id = uuid4()
    user_id = uuid4()
    ok = AutomationWorkflow(
        organization_id=org_id,
        name="OK",
        status="draft",
        draft_version=1,
        draft_definition={
            "trigger": "customer_message_received",
            "actions": [{"kind": "set_priority", "value": "high"}],
        },
        created_by_user_id=user_id,
    )
    ok.id = uuid4()

    out = _workflow_out_or_skip_invalid(ok)
    assert out is not None
    assert out.name == "OK"
    assert out.definition.actions[0].kind == "set_priority"
