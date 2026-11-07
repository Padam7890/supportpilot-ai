"""Pure, deterministic automation matching and preview policy."""

from dataclasses import dataclass
from uuid import UUID

from app.features.automations.contracts import (
    Action,
    AutomationPreviewActionOut,
    AutomationPreviewConditionOut,
    AutomationPreviewOut,
    AutomationPreviewStepOut,
    Condition,
    WorkflowDefinition,
)


@dataclass(frozen=True)
class EvaluationContext:
    message: str
    ticket_priority: str
    ticket_status: str
    channel: str
    is_first_customer_message: bool
    assignee_present: bool
    conversation_ai_mode: str
    shopify_connected: bool
    trigger_ai_agent_id: UUID | None
    trigger_integration_connection_id: UUID | None
    conversation_ai_agent_id: UUID | None
    conversation_integration_connection_id: UUID | None


PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2, "urgent": 3}
MAX_TOTAL_EXECUTION_ATTEMPTS = 5


def _normalize_text(value: str) -> str:
    return value.casefold()


def evaluate_one_condition(condition: Condition, ctx: EvaluationContext) -> bool:
    if condition.kind == "contains_keyword":
        return condition.value.casefold() in _normalize_text(ctx.message)
    if condition.kind == "ticket_priority_is":
        actual = ctx.ticket_priority
        matches = actual == condition.value
        return matches if condition.operator == "is" else not matches
    if condition.kind == "ticket_status_is":
        actual_cf = _normalize_text(ctx.ticket_status)
        target_cf = _normalize_text(condition.value)
        matches = actual_cf == target_cf
        return matches if condition.operator == "is" else not matches
    if condition.kind == "channel_is":
        actual_cf = _normalize_text(ctx.channel)
        target_cf = _normalize_text(condition.value)
        matches = actual_cf == target_cf
        return matches if condition.operator == "is" else not matches
    if condition.kind == "conversation_ai_mode_is":
        return _normalize_text(ctx.conversation_ai_mode) == _normalize_text(condition.mode)
    if condition.kind == "assignee_present":
        return ctx.assignee_present == condition.value
    if condition.kind == "shopify_store_connected":
        return ctx.shopify_connected
    return False


def evaluate_conditions(definition: WorkflowDefinition, ctx: EvaluationContext) -> bool:
    if not _trigger_matches(definition, ctx):
        return False
    return _condition_group_matches(definition, ctx)


def _trigger_matches(definition: WorkflowDefinition, ctx: EvaluationContext) -> bool:
    if definition.trigger.kind != "customer_message_received":
        return False
    trig = definition.trigger
    if trig.first_message_only and not ctx.is_first_customer_message:
        return False
    if trig.channel is not None:
        need = _normalize_text(trig.channel.strip())
        if _normalize_text(ctx.channel) != need:
            return False
    if trig.ai_agent_id is not None and trig.ai_agent_id != ctx.conversation_ai_agent_id:
        return False
    if (
        trig.integration_connection_id is not None
        and trig.integration_connection_id != ctx.conversation_integration_connection_id
    ):
        return False
    return True


def _condition_group_matches(definition: WorkflowDefinition, ctx: EvaluationContext) -> bool:
    conds = definition.conditions
    if not conds:
        return True
    results = [evaluate_one_condition(c, ctx) for c in conds]
    if definition.condition_mode == "any":
        return any(results)
    return all(results)


def _condition_label(condition: Condition) -> str:
    if condition.kind == "contains_keyword":
        return f'Message contains “{condition.value}”'
    if condition.kind == "ticket_priority_is":
        op = "is" if condition.operator == "is" else "is not"
        return f"Ticket priority {op} {condition.value}"
    if condition.kind == "ticket_status_is":
        op = "is" if condition.operator == "is" else "is not"
        return f"Ticket status {op} {condition.value}"
    if condition.kind == "channel_is":
        op = "is" if condition.operator == "is" else "is not"
        return f"Channel {op} {condition.value}"
    if condition.kind == "conversation_ai_mode_is":
        return f"Conversation AI mode is {condition.mode}"
    if condition.kind == "assignee_present":
        return "Assignee is set" if condition.value else "Assignee is not set"
    if condition.kind == "shopify_store_connected":
        return "Shopify store is connected"
    return condition.kind


def _condition_preview_match(condition: Condition, ctx: EvaluationContext) -> bool:
    return evaluate_one_condition(condition, ctx)


def _trigger_blocked(definition: WorkflowDefinition, ctx: EvaluationContext) -> tuple[bool, str | None]:
    if definition.trigger.kind != "customer_message_received":
        return True, "This trigger is not available for message preview yet."
    trig = definition.trigger
    if trig.first_message_only and not ctx.is_first_customer_message:
        return True, "Trigger is limited to the customer's first message in the conversation."
    if trig.channel is not None:
        need = trig.channel.strip()
        if _normalize_text(ctx.channel) != _normalize_text(need):
            return True, f"Trigger is limited to channel “{need}”."
    if trig.ai_agent_id is not None and trig.ai_agent_id != ctx.conversation_ai_agent_id:
        return True, "Trigger is limited to a specific AI bot."
    if (
        trig.integration_connection_id is not None
        and trig.integration_connection_id != ctx.conversation_integration_connection_id
    ):
        return True, "Trigger is limited to a specific channel connection."
    return False, None


def preview_definition(
    definition: WorkflowDefinition,
    *,
    message: str,
    current_ticket_priority: str | None = None,
    current_ticket_status: str | None = None,
    channel: str | None = None,
    is_first_customer_message: bool | None = None,
    assignee_present: bool | None = None,
    conversation_ai_mode: str | None = None,
    shopify_connected: bool | None = None,
    conversation_ai_agent_id: UUID | None = None,
    conversation_integration_connection_id: UUID | None = None,
) -> AutomationPreviewOut:
    ctx = EvaluationContext(
        message=message,
        ticket_priority=current_ticket_priority or "normal",
        ticket_status=current_ticket_status or "open",
        channel=channel or "web",
        is_first_customer_message=(
            is_first_customer_message if is_first_customer_message is not None else True
        ),
        assignee_present=assignee_present if assignee_present is not None else False,
        conversation_ai_mode=conversation_ai_mode or "human",
        shopify_connected=shopify_connected if shopify_connected is not None else False,
        trigger_ai_agent_id=definition.trigger.ai_agent_id
        if definition.trigger.kind == "customer_message_received"
        else None,
        trigger_integration_connection_id=definition.trigger.integration_connection_id
        if definition.trigger.kind == "customer_message_received"
        else None,
        conversation_ai_agent_id=conversation_ai_agent_id,
        conversation_integration_connection_id=conversation_integration_connection_id,
    )

    steps: list[AutomationPreviewStepOut] = []

    blocked, block_reason = _trigger_blocked(definition, ctx)
    if blocked:
        steps.append(AutomationPreviewStepOut(step="trigger", outcome="skipped", detail=block_reason or ""))
        return AutomationPreviewOut(
            matches=False,
            condition_mode=definition.condition_mode,
            conditions=[],
            planned_actions=[],
            steps=steps,
        )

    steps.append(AutomationPreviewStepOut(step="trigger", outcome="matched", detail="Incoming customer message"))

    condition_rows: list[AutomationPreviewConditionOut] = []
    for condition in definition.conditions:
        matched = _condition_preview_match(condition, ctx)
        condition_rows.append(
            AutomationPreviewConditionOut(
                kind=condition.kind,
                label=_condition_label(condition),
                matched=matched,
            )
        )

    if definition.conditions:
        cond_outcomes = [c.matched for c in condition_rows]
        group_ok = any(cond_outcomes) if definition.condition_mode == "any" else all(cond_outcomes)
        detail = (
            "Match any condition passed"
            if definition.condition_mode == "any" and group_ok
            else "All conditions matched"
            if definition.condition_mode == "all" and group_ok
            else "Condition group did not match"
        )
        steps.append(
            AutomationPreviewStepOut(
                step=f"conditions ({definition.condition_mode})",
                outcome="matched" if group_ok else "skipped",
                detail=detail,
            )
        )
        for row in condition_rows:
            steps.append(
                AutomationPreviewStepOut(
                    step=row.label,
                    outcome="matched" if row.matched else "skipped",
                    detail="Matched" if row.matched else "Not matched",
                )
            )
    else:
        group_ok = True
        steps.append(
            AutomationPreviewStepOut(
                step="conditions",
                outcome="matched",
                detail="No conditions — runs on every matching trigger event",
            )
        )

    selected_branch = "match" if group_ok else "no_match" if definition.else_actions else None
    matches = group_ok or bool(definition.else_actions)
    selected_actions = definition.actions if group_ok else definition.else_actions
    planned: list[AutomationPreviewActionOut] = []
    if matches:
        if selected_branch is not None:
            steps.append(
                AutomationPreviewStepOut(
                    step=f"branch:{selected_branch}",
                    outcome="matched",
                    detail="Selected the condition-matched path" if group_ok else "Selected the no-match path",
                )
            )
        current_p = ctx.ticket_priority
        for action in selected_actions:
            planned.append(_preview_action(action, current_priority=current_p))
            current_p = _priority_after_action(action, current_p)
            steps.append(
                AutomationPreviewStepOut(
                    step=f"action:{action.kind}",
                    outcome="would_run",
                    detail=planned[-1].summary,
                )
            )
    else:
        for action in definition.actions:
            steps.append(
                AutomationPreviewStepOut(
                    step=f"action:{action.kind}",
                    outcome="skipped",
                    detail="Skipped because conditions did not match",
                )
            )

    return AutomationPreviewOut(
        matches=matches,
        condition_mode=definition.condition_mode,
        conditions=condition_rows,
        planned_actions=planned,
        steps=steps,
        selected_branch=selected_branch,
    )


def _preview_action(action: Action, *, current_priority: str) -> AutomationPreviewActionOut:
    if action.kind == "set_priority":
        if action.only_raise:
            current_rank = PRIORITY_RANK.get(current_priority, 1)
            target_rank = PRIORITY_RANK[action.value]
            if target_rank <= current_rank:
                return AutomationPreviewActionOut(
                    kind="set_priority",
                    summary=f"Keep priority at {current_priority} (only_raise: target is not higher)",
                    outcome="skipped",
                    detail="only_raise",
                )
        if current_priority == action.value:
            return AutomationPreviewActionOut(
                kind="set_priority",
                summary=f"No change: ticket is already {action.value} priority",
                outcome="skipped",
                detail="same_priority",
            )
        return AutomationPreviewActionOut(
            kind="set_priority",
            summary=f"Set ticket priority to {action.value}",
            outcome="would_run",
        )
    if action.kind == "assign_to_user":
        return AutomationPreviewActionOut(
            kind="assign_to_user",
            summary="Assign ticket to the selected teammate",
            outcome="would_run",
        )
    if action.kind == "assign_to_team":
        return AutomationPreviewActionOut(
            kind="assign_to_team",
            summary="Route ticket to the selected support team",
            outcome="would_run",
            detail="An assignee outside the selected team will be cleared.",
        )
    if action.kind == "set_ticket_status":
        return AutomationPreviewActionOut(
            kind="set_ticket_status",
            summary=f"Set ticket status to {action.value}",
            outcome="would_run",
        )
    if action.kind == "set_conversation_ai_mode":
        return AutomationPreviewActionOut(
            kind="set_conversation_ai_mode",
            summary=f"Set conversation AI mode to {action.mode}",
            outcome="would_run",
        )
    if action.kind == "route_to_ai_bot":
        return AutomationPreviewActionOut(
            kind="route_to_ai_bot",
            summary="Route future Shopify widget replies to the selected active AI bot",
            outcome="would_run",
            detail="This does not change an AI reply already queued for the current message.",
        )
    if action.kind == "restore_widget_bot_routing":
        return AutomationPreviewActionOut(
            kind="restore_widget_bot_routing",
            summary="Resume the widget's configured multi-bot routing",
            outcome="would_run",
        )
    if action.kind == "add_internal_note":
        return AutomationPreviewActionOut(
            kind="add_internal_note",
            summary="Add an internal note on the conversation",
            outcome="would_run",
        )
    if action.kind == "require_human_approval":
        return AutomationPreviewActionOut(
            kind="require_human_approval",
            summary=action.summary,
            outcome="would_run",
            detail="The workflow pauses here until an Owner/Admin reviews the run.",
        )
    if action.kind == "request_commerce_approval":
        return AutomationPreviewActionOut(
            kind="request_commerce_approval",
            summary=action.summary,
            outcome="would_run",
        )
    if action.kind == "lookup_shopify_order":
        return AutomationPreviewActionOut(
            kind="lookup_shopify_order",
            summary="Look up order from message text (Shopify, read-only)",
            outcome="would_run",
        )
    if action.kind == "search_shopify_catalog":
        return AutomationPreviewActionOut(
            kind="search_shopify_catalog",
            summary="Search Shopify catalog (read-only)",
            outcome="would_run",
        )
    return AutomationPreviewActionOut(kind=action.kind, summary=action.kind, outcome="would_run")


def _priority_after_action(action: Action, current: str) -> str:
    if action.kind == "set_priority":
        if action.only_raise:
            cr = PRIORITY_RANK.get(current, 1)
            tr = PRIORITY_RANK[action.value]
            return action.value if tr > cr else current
        return action.value
    return current


def evaluation_context_from_runtime(
    *,
    message_content: str,
    ticket_priority: str,
    ticket_status: str,
    channel: str,
    is_first_customer_message: bool,
    assignee_present: bool,
    conversation_ai_mode: str,
    shopify_connected: bool,
    conversation_ai_agent_id: UUID | None,
    conversation_integration_connection_id: UUID | None,
) -> EvaluationContext:
    return EvaluationContext(
        message=message_content,
        ticket_priority=ticket_priority,
        ticket_status=ticket_status,
        channel=channel,
        is_first_customer_message=is_first_customer_message,
        assignee_present=assignee_present,
        conversation_ai_mode=conversation_ai_mode,
        shopify_connected=shopify_connected,
        trigger_ai_agent_id=None,
        trigger_integration_connection_id=None,
        conversation_ai_agent_id=conversation_ai_agent_id,
        conversation_integration_connection_id=conversation_integration_connection_id,
    )


def evaluate_customer_message_match(
    definition: WorkflowDefinition,
    ctx: EvaluationContext,
) -> bool:
    if definition.trigger.kind != "customer_message_received":
        return False
    # Fill trigger ids from definition for evaluate_conditions
    merged = EvaluationContext(
        message=ctx.message,
        ticket_priority=ctx.ticket_priority,
        ticket_status=ctx.ticket_status,
        channel=ctx.channel,
        is_first_customer_message=ctx.is_first_customer_message,
        assignee_present=ctx.assignee_present,
        conversation_ai_mode=ctx.conversation_ai_mode,
        shopify_connected=ctx.shopify_connected,
        trigger_ai_agent_id=definition.trigger.ai_agent_id
        if definition.trigger.kind == "customer_message_received"
        else None,
        trigger_integration_connection_id=definition.trigger.integration_connection_id
        if definition.trigger.kind == "customer_message_received"
        else None,
        conversation_ai_agent_id=ctx.conversation_ai_agent_id,
        conversation_integration_connection_id=ctx.conversation_integration_connection_id,
    )
    return evaluate_conditions(definition, merged)


def evaluate_customer_message_branch(
    definition: WorkflowDefinition,
    ctx: EvaluationContext,
) -> str | None:
    """Return the matching path, with None reserved for a non-matching trigger."""
    if definition.trigger.kind != "customer_message_received":
        return None
    merged = EvaluationContext(
        message=ctx.message,
        ticket_priority=ctx.ticket_priority,
        ticket_status=ctx.ticket_status,
        channel=ctx.channel,
        is_first_customer_message=ctx.is_first_customer_message,
        assignee_present=ctx.assignee_present,
        conversation_ai_mode=ctx.conversation_ai_mode,
        shopify_connected=ctx.shopify_connected,
        trigger_ai_agent_id=definition.trigger.ai_agent_id,
        trigger_integration_connection_id=definition.trigger.integration_connection_id,
        conversation_ai_agent_id=ctx.conversation_ai_agent_id,
        conversation_integration_connection_id=ctx.conversation_integration_connection_id,
    )
    if not _trigger_matches(definition, merged):
        return None
    return "match" if _condition_group_matches(definition, merged) else "no_match"
