"""Application services for workflow event enqueueing and validation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import current_correlation_id
from app.features.automations.capabilities import organization_capabilities
from app.features.automations.contracts import Action, SUPPORTED_TICKET_STATUSES, WorkflowDefinition
from app.models import AIAgent, AutomationExecution, AutomationWorkflow, AutomationWorkflowVersion, Conversation, IntegrationConnection, Message, Team, User


def _all_actions(definition: WorkflowDefinition) -> list[Action]:
    branch_actions = [action for branch in definition.branches for action in branch.actions]
    return [*definition.actions, *branch_actions, *definition.else_actions]


def _all_conditions(definition: WorkflowDefinition):
    return [*definition.conditions, *(condition for branch in definition.branches for condition in branch.conditions)]


async def validate_assignment_targets(
    db: AsyncSession, organization_id: UUID, definition: WorkflowDefinition
) -> None:
    """Validate assign_to_user targets belong to the tenant."""
    user_ids = {
        action.user_id
        for action in _all_actions(definition)
        if action.kind == "assign_to_user"
    }
    if not user_ids:
        return
    found = set(
        await db.scalars(
            select(User.id).where(
                User.organization_id == organization_id,
                User.id.in_(user_ids),
                User.is_active.is_(True),
                User.role.in_(("owner", "admin", "agent")),
            )
        )
    )
    if found != user_ids:
        raise ValueError("Assignment actions must target active members of this workspace")


async def validate_team_assignment_targets(
    db: AsyncSession, organization_id: UUID, definition: WorkflowDefinition
) -> None:
    """Validate automation team targets are active and tenant-owned."""
    team_ids = {
        action.team_id
        for action in _all_actions(definition)
        if action.kind == "assign_to_team"
    }
    if not team_ids:
        return
    found = set(
        await db.scalars(
            select(Team.id).where(
                Team.organization_id == organization_id,
                Team.id.in_(team_ids),
                Team.is_active.is_(True),
            )
        )
    )
    if found != team_ids:
        raise ValueError("Assignment actions must target active teams in this workspace")


def _normalize_channel(value: str) -> str:
    return value.strip().casefold()


async def validate_definition_targets(
    db: AsyncSession, organization_id: UUID, definition: WorkflowDefinition
) -> None:
    """Validate workflow before publish."""
    if definition.trigger.kind not in ("customer_message_received", "conversation_started"):
        raise ValueError("This workflow trigger is not available in this release")
    await validate_assignment_targets(db, organization_id, definition)
    await validate_team_assignment_targets(db, organization_id, definition)

    unsupported_statuses = {
        action.value.strip().casefold()
        for action in _all_actions(definition)
        if action.kind == "set_ticket_status"
        and action.value.strip().casefold() not in SUPPORTED_TICKET_STATUSES
    }
    unsupported_status_conditions = {
        condition.value.strip().casefold()
        for condition in _all_conditions(definition)
        if condition.kind == "ticket_status_is"
        and condition.value.strip().casefold() not in SUPPORTED_TICKET_STATUSES
    }
    if unsupported_statuses:
        allowed = ", ".join(sorted(SUPPORTED_TICKET_STATUSES))
        raise ValueError(f"Ticket status actions must use one of: {allowed}")
    if unsupported_status_conditions:
        allowed = ", ".join(sorted(SUPPORTED_TICKET_STATUSES))
        raise ValueError(f"Ticket status conditions must use one of: {allowed}")

    agent_ids = {
        action.ai_agent_id
        for action in _all_actions(definition)
        if action.kind == "route_to_ai_bot"
    }
    if agent_ids:
        active_agent_ids = set(
            await db.scalars(
                select(AIAgent.id).where(
                    AIAgent.organization_id == organization_id,
                    AIAgent.id.in_(agent_ids),
                    AIAgent.status == "active",
                )
            )
        )
        if active_agent_ids != agent_ids:
            raise ValueError("Bot routing actions must target active AI bots in this workspace")

    caps = await organization_capabilities(db, organization_id)

    if definition.trigger.kind == "customer_message_received" and definition.trigger.ai_agent_id is not None:
        agent = await db.scalar(
            select(AIAgent.id).where(
                AIAgent.organization_id == organization_id,
                AIAgent.id == definition.trigger.ai_agent_id,
            )
        )
        if agent is None:
            raise ValueError("Trigger references an unknown AI agent for this workspace")

    if (
        definition.trigger.kind == "customer_message_received"
        and definition.trigger.integration_connection_id is not None
    ):
        conn = await db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.id == definition.trigger.integration_connection_id,
                IntegrationConnection.status == "connected",
            )
        )
        if conn is None:
            raise ValueError("Trigger references an unknown or disconnected channel connection")

    needs_shopify = any(c.kind == "shopify_store_connected" for c in _all_conditions(definition)) or any(
        a.kind in ("lookup_shopify_order", "search_shopify_catalog", "request_commerce_approval")
        for a in _all_actions(definition)
    )
    if needs_shopify and "shopify.read" not in caps:
        raise ValueError("Connect a Shopify store to publish workflows that use Shopify conditions or actions")


async def enqueue_customer_message_workflows(
    db: AsyncSession,
    *,
    organization_id: UUID,
    ticket_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
) -> int:
    """Create durable runs for message triggers and first-message conversation triggers."""
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.id == conversation_id,
        ).with_for_update()
    )
    if conversation is None:
        return 0

    message = await db.scalar(
        select(Message).where(
            Message.organization_id == organization_id,
            Message.conversation_id == conversation_id,
            Message.id == message_id,
            Message.sender_type == "customer",
        )
    )
    if message is None:
        return 0

    first_customer_message_id = await db.scalar(
        select(Message.id)
        .where(
            Message.organization_id == organization_id,
            Message.conversation_id == conversation_id,
            Message.sender_type == "customer",
        )
        .order_by(Message.created_at, Message.id)
        .limit(1)
    )
    is_first_customer_message = first_customer_message_id == message_id

    workflows = await db.execute(
        select(AutomationWorkflow.id, AutomationWorkflowVersion.id, AutomationWorkflowVersion.definition)
        .join(
            AutomationWorkflowVersion,
            (AutomationWorkflowVersion.organization_id == AutomationWorkflow.organization_id)
            & (AutomationWorkflowVersion.workflow_id == AutomationWorkflow.id)
            & (AutomationWorkflowVersion.version == AutomationWorkflow.published_version),
        )
        .where(
            AutomationWorkflow.organization_id == organization_id,
            AutomationWorkflow.status == "active",
            AutomationWorkflow.published_version.is_not(None),
            AutomationWorkflowVersion.definition["trigger"]["kind"].as_string().in_(
                ("customer_message_received", "conversation_started")
            ),
        )
        .order_by(AutomationWorkflow.created_at, AutomationWorkflow.id)
        .limit(100)
    )
    count = 0
    for workflow_id, version_id, definition_raw in workflows.all():
        definition = WorkflowDefinition.model_validate(definition_raw)
        trig = definition.trigger
        if trig.kind == "conversation_started" and not is_first_customer_message:
            continue
        if trig.kind == "customer_message_received":
            if trig.channel is not None and _normalize_channel(trig.channel) != _normalize_channel(
                conversation.channel
            ):
                continue
            if trig.ai_agent_id is not None and trig.ai_agent_id != conversation.ai_agent_id:
                continue
            if (
                trig.integration_connection_id is not None
                and trig.integration_connection_id != conversation.integration_connection_id
            ):
                continue
        inserted = await db.scalar(
            pg_insert(AutomationExecution)
            .values(
                organization_id=organization_id,
                workflow_id=workflow_id,
                version_id=version_id,
                conversation_id=conversation_id,
                ticket_id=ticket_id,
                source_message_id=message_id,
                event_key=(
                    f"conversation:{conversation_id}"
                    if trig.kind == "conversation_started"
                    else str(message_id)
                ),
                correlation_id=current_correlation_id(),
            )
            .on_conflict_do_nothing(constraint="uq_automation_executions_event")
            .returning(AutomationExecution.id)
        )
        count += int(inserted is not None)
    return count
