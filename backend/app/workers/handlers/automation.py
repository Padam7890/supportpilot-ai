"""Durable automation execution worker for the allowlisted workflow actions."""

import logging
import random
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, set_tenant_context
from app.features.automations.capabilities import organization_capabilities
from app.features.automations.approvals import expire_pending_automation_approvals
from app.features.automations.contracts import (
    Action,
    SUPPORTED_TICKET_STATUSES,
    WorkflowDefinition,
)
from app.features.automations.policy import (
    PRIORITY_RANK,
    evaluate_customer_message_branch,
    evaluation_context_from_runtime,
)
from app.features.automations.shopify_actions import (
    extract_catalog_query,
    extract_order_number,
    read_shopify_catalog_titles,
    read_shopify_order_summary,
    ticket_customer_email,
)
from app.features.automations.shopify_automation_approval import request_verified_shopify_cancellation
from app.models import (
    AutomationExecution,
    AutomationExecutionApproval,
    AutomationExecutionEffect,
    AutomationWorkflowVersion,
    AIAgent,
    Conversation,
    Message,
    ShopifyInstallation,
    Team,
    TeamMember,
    Ticket,
    TicketActivity,
    User,
)
from app.workers.application.contracts import ClaimedJob, JobHandler

LEASE_DURATION = timedelta(minutes=2)
MAX_RETRY_SECONDS = 300
logger = logging.getLogger(__name__)


def retry_delay_seconds(attempt: int, *, random_value: float | None = None) -> int:
    """Bounded exponential retry delay with jitter for transient DB/provider faults."""
    if attempt < 1:
        raise ValueError("attempt must be positive")
    jitter = random.random() if random_value is None else min(1.0, max(0.0, random_value))
    ceiling = min(MAX_RETRY_SECONDS, 2 ** min(attempt, 8))
    return max(1, int(ceiling * jitter))


class AutomationExecutionHandler(JobHandler):
    kind = "automation"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            now = datetime.now(UTC)
            expired_approvals = await expire_pending_automation_approvals(
                db, organization_id, now=now
            )
            execution = await db.scalar(
                select(AutomationExecution)
                .where(
                    AutomationExecution.organization_id == organization_id,
                    or_(
                        and_(
                            AutomationExecution.status == "queued",
                            AutomationExecution.next_attempt_at <= now,
                            AutomationExecution.attempt_count < AutomationExecution.max_attempts,
                        ),
                        and_(
                            AutomationExecution.status == "running",
                            AutomationExecution.locked_until < now,
                        ),
                    ),
                )
                .order_by(AutomationExecution.next_attempt_at, AutomationExecution.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if execution is None:
                if expired_approvals:
                    await db.commit()
                return None
            if execution.attempt_count >= execution.max_attempts:
                execution.status = "failed"
                execution.error_code = "automation_execution_failed"
                execution.locked_until = None
                execution.lease_token = None
                execution.completed_at = now
                await db.commit()
                return None
            claim_token = uuid4()
            execution.status = "running"
            execution.attempt_count += 1
            execution.locked_until = now + LEASE_DURATION
            execution.lease_token = claim_token
            execution.started_at = execution.started_at or now
            await db.commit()
            return ClaimedJob(
                self.kind,
                organization_id,
                execution.id,
                event_name="automation_trigger",
                correlation_id=execution.correlation_id,
                claim_token=claim_token,
            )

    async def process(self, job: ClaimedJob) -> None:
        if job.job_id is None or job.claim_token is None:
            raise ValueError("Automation execution ID and claim token are required")
        try:
            async with SessionLocal() as db:
                await set_tenant_context(db, job.organization_id)
                execution = await db.scalar(
                    select(AutomationExecution)
                    .where(
                        AutomationExecution.organization_id == job.organization_id,
                        AutomationExecution.id == job.job_id,
                        AutomationExecution.status == "running",
                        AutomationExecution.lease_token == job.claim_token,
                    )
                    .with_for_update()
                )
                if execution is None:
                    return
                version = await db.scalar(
                    select(AutomationWorkflowVersion).where(
                        AutomationWorkflowVersion.organization_id == job.organization_id,
                        AutomationWorkflowVersion.id == execution.version_id,
                    )
                )
                message = await db.scalar(
                    select(Message).where(
                        Message.organization_id == job.organization_id,
                        Message.id == execution.source_message_id,
                        Message.conversation_id == execution.conversation_id,
                        Message.sender_type == "customer",
                    )
                )
                conversation = await db.scalar(
                    select(Conversation).where(
                        Conversation.organization_id == job.organization_id,
                        Conversation.id == execution.conversation_id,
                    )
                )
                ticket = await db.scalar(
                    select(Ticket)
                    .where(
                        Ticket.organization_id == job.organization_id,
                        Ticket.id == execution.ticket_id,
                    )
                    .with_for_update()
                )
                if version is None or message is None or ticket is None or conversation is None:
                    raise RuntimeError("automation_source_unavailable")
                definition = WorkflowDefinition.model_validate(version.definition)
                prior_customer_messages = await db.scalar(
                    select(func.count(Message.id)).where(
                        Message.organization_id == job.organization_id,
                        Message.conversation_id == message.conversation_id,
                        Message.sender_type == "customer",
                        or_(
                            Message.created_at < message.created_at,
                            and_(
                                Message.created_at == message.created_at,
                                Message.id < message.id,
                            ),
                        ),
                    )
                )
                is_first_customer_message = int(prior_customer_messages or 0) == 0
                caps = await organization_capabilities(db, job.organization_id)
                shopify_n = await db.scalar(
                    select(func.count())
                    .select_from(ShopifyInstallation)
                    .where(
                        ShopifyInstallation.organization_id == job.organization_id,
                        ShopifyInstallation.disconnected_at.is_(None),
                    )
                )
                shopify_connected = int(shopify_n or 0) > 0
                ctx = evaluation_context_from_runtime(
                    message_content=message.content,
                    ticket_priority=ticket.priority,
                    ticket_status=ticket.status,
                    channel=conversation.channel,
                    is_first_customer_message=is_first_customer_message,
                    assignee_present=ticket.assignee_id is not None,
                    conversation_ai_mode=conversation.ai_mode,
                    shopify_connected=shopify_connected,
                    conversation_ai_agent_id=conversation.ai_agent_id,
                    conversation_integration_connection_id=conversation.integration_connection_id,
                )
                valid_branch_selections = {
                    "match",
                    "no_match",
                    *(f"branch:{branch.id}" for branch in definition.branches),
                }
                persisted_branch = next(
                    (
                        item.get("detail")
                        for item in execution.result
                        if isinstance(item, dict)
                        and item.get("action") == "branch_selection"
                        and item.get("detail") in valid_branch_selections
                    ),
                    None,
                )
                selected_branch = persisted_branch or evaluate_customer_message_branch(definition, ctx)

                if selected_branch is None:
                    execution.result = [{
                        "action": "trigger",
                        "outcome": "skipped",
                        "detail": "Message did not match the workflow trigger",
                    }]
                elif selected_branch == "no_match" and not definition.else_actions:
                    execution.result = [{
                        "action": "conditions",
                        "outcome": "skipped",
                        "detail": "Message did not match the workflow conditions",
                    }]
                else:
                    if persisted_branch is None and (definition.conditions or definition.branches or definition.else_actions):
                        execution.result = [{
                            "action": "branch_selection",
                            "outcome": "applied",
                            "detail": selected_branch,
                        }]
                    branch = next(
                        (item for item in definition.branches if selected_branch == f"branch:{item.id}"),
                        None,
                    )
                    selected_actions = (
                        definition.actions
                        if selected_branch == "match"
                        else branch.actions
                        if branch is not None
                        else definition.else_actions
                    )
                    execution.result = _merge_action_results(
                        execution.result,
                        await _apply_actions(
                            db,
                            organization_id=job.organization_id,
                            execution_id=execution.id,
                            conversation_id=conversation.id,
                            message_content=message.content,
                            capabilities=caps,
                            shopify_connected=shopify_connected,
                            customer_email=await ticket_customer_email(db, job.organization_id, ticket.id),
                            ticket=ticket,
                            conversation=conversation,
                            actions=selected_actions,
                        ),
                    )
                outcomes = execution.result
                waiting_for_approval = any(
                    item.get("outcome") == "waiting_approval" for item in outcomes
                )
                rejected = any(item.get("outcome") == "rejected" for item in outcomes)
                execution.status = (
                    "rejected" if rejected else "waiting_approval" if waiting_for_approval else "succeeded"
                )
                execution.error_code = None
                execution.locked_until = None
                execution.lease_token = None
                execution.completed_at = None if waiting_for_approval else datetime.now(UTC)
                await db.commit()
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning(
                "automation_execution_attempt_failed",
                extra={
                    "organization_id": str(job.organization_id),
                    "execution_id": str(job.job_id),
                    "correlation_id": job.correlation_id,
                    "error_type": type(exc).__name__,
                },
            )
            await self._record_failure(job)

    async def _record_failure(self, job: ClaimedJob) -> None:
        async with SessionLocal() as db:
            await set_tenant_context(db, job.organization_id)
            execution = await db.scalar(
                select(AutomationExecution)
                .where(
                    AutomationExecution.organization_id == job.organization_id,
                    AutomationExecution.id == job.job_id,
                    AutomationExecution.status == "running",
                    AutomationExecution.lease_token == job.claim_token,
                )
                .with_for_update()
            )
            if execution is None:
                return
            now = datetime.now(UTC)
            execution.error_code = "automation_execution_failed"
            execution.locked_until = None
            execution.lease_token = None
            if execution.attempt_count >= execution.max_attempts:
                execution.status = "failed"
                execution.completed_at = now
            else:
                execution.status = "queued"
                execution.next_attempt_at = now + timedelta(
                    seconds=retry_delay_seconds(execution.attempt_count)
                )
            await db.commit()


async def _claim_effect(
    db: AsyncSession,
    organization_id: UUID,
    execution_id: UUID,
    effect_key: str,
) -> bool:
    """Return True if this execution may apply the effect once; False if already applied."""
    row_id = await db.scalar(
        pg_insert(AutomationExecutionEffect)
        .values(
            organization_id=organization_id,
            execution_id=execution_id,
            effect_key=effect_key,
        )
        .on_conflict_do_nothing(constraint="uq_automation_execution_effects_org_exec_key")
        .returning(AutomationExecutionEffect.id)
    )
    return row_id is not None


def _merge_action_results(
    previous: list[dict[str, object]], current: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Keep successful prior step outcomes when an approved execution resumes."""
    prior = {
        item.get("action_index"): item
        for item in previous
        if isinstance(item, dict) and isinstance(item.get("action_index"), int)
    }
    markers = [
        item
        for item in previous
        if isinstance(item, dict) and item.get("action") == "branch_selection"
    ]
    merged: list[dict[str, object]] = []
    for item in current:
        index = item.get("action_index")
        old = prior.get(index)
        if (
            old is not None
            and old.get("outcome") == "applied"
            and item.get("outcome") == "skipped"
            and item.get("detail") == "Already applied (idempotent replay)"
        ):
            merged.append(old)
        else:
            merged.append(item)
    return [*markers, *merged]


async def _append_internal_note(
    db: AsyncSession,
    organization_id: UUID,
    conversation_id: UUID,
    body: str,
) -> None:
    note = Message(
        organization_id=organization_id,
        conversation_id=conversation_id,
        sender_type="system",
        sender_user_id=None,
        content=body.strip(),
        content_type="text",
    )
    conv = await db.scalar(
        select(Conversation)
        .where(
            Conversation.organization_id == organization_id,
            Conversation.id == conversation_id,
        )
        .with_for_update()
    )
    if conv is None:
        raise RuntimeError("automation_conversation_unavailable")
    conv.updated_at = datetime.now(UTC)
    db.add(note)


async def _apply_actions(
    db: AsyncSession,
    *,
    organization_id: UUID,
    execution_id: UUID,
    conversation_id: UUID,
    message_content: str,
    capabilities: frozenset[str],
    shopify_connected: bool,
    customer_email: str | None,
    ticket: Ticket,
    conversation: Conversation,
    actions: list[Action],
) -> list[dict[str, object]]:
    outcomes: list[dict[str, object]] = []
    for index, action in enumerate(actions):
        before: dict[str, str | None]
        after: dict[str, str | None]
        effect_key = f"action:{index}:{action.kind}"
        if action.kind == "require_human_approval":
            approval = await db.scalar(
                select(AutomationExecutionApproval)
                .where(
                    AutomationExecutionApproval.organization_id == organization_id,
                    AutomationExecutionApproval.execution_id == execution_id,
                    AutomationExecutionApproval.action_index == index,
                )
                .with_for_update()
            )
            if approval is None:
                approval = AutomationExecutionApproval(
                    organization_id=organization_id,
                    execution_id=execution_id,
                    action_index=index,
                    summary=action.summary,
                    detail=action.detail,
                    status="pending",
                )
                db.add(approval)
                db.add(TicketActivity(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    actor_user_id=None,
                    activity_type="automation_approval_requested",
                    details={
                        "execution_id": str(execution_id),
                        "action_index": index,
                        "summary": action.summary,
                    },
                ))
                await db.flush()
            if approval.status == "approved":
                outcomes.append({
                    "action": action.kind,
                    "outcome": "approved",
                    "detail": "Approved by a workspace Owner/Admin",
                })
                continue
            if approval.status == "rejected":
                outcomes.append({
                    "action": action.kind,
                    "outcome": "rejected",
                    "detail": "Rejected by a workspace Owner/Admin",
                })
                break
            outcomes.append({
                "action": action.kind,
                "outcome": "waiting_approval",
                "detail": "Waiting for workspace Owner/Admin review",
            })
            break
        if action.kind == "set_priority":
            before = {"priority": ticket.priority}
            next_priority = action.value
            if action.only_raise:
                current_rank = PRIORITY_RANK.get(ticket.priority, 1)
                target_rank = PRIORITY_RANK[action.value]
                if target_rank <= current_rank:
                    outcomes.append({
                        "action": action.kind,
                        "outcome": "skipped",
                        "detail": "Ticket priority already at or above target",
                    })
                    continue
            if ticket.priority == next_priority:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Ticket already had this value",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            ticket.priority = next_priority
            after = {"priority": ticket.priority}
            db.add(TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=None,
                activity_type="automation_action",
                details={"action": action.kind, "before": before, "after": after},
            ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": "Ticket updated",
            })
        elif action.kind == "assign_to_user":
            if action.only_if_unassigned and ticket.assignee_id is not None:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Ticket already assigned",
                })
                continue
            member = await db.scalar(
                select(User).where(
                    User.organization_id == organization_id,
                    User.id == action.user_id,
                    User.is_active.is_(True),
                    User.role.in_(("owner", "admin", "agent")),
                )
            )
            if member is None:
                raise RuntimeError("automation_assignment_target_unavailable")
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before = {"assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None}
            ticket.assignee_id = member.id
            after = {"assignee_id": str(member.id)}
            if before != after:
                db.add(TicketActivity(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    actor_user_id=None,
                    activity_type="automation_action",
                    details={"action": action.kind, "before": before, "after": after},
                ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied" if before != after else "skipped",
                "detail": "Ticket updated" if before != after else "Ticket already had this value",
            })
        elif action.kind == "assign_to_team":
            if action.only_if_unassigned and ticket.team_id is not None:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Ticket already has a team",
                })
                continue
            team = await db.scalar(
                select(Team).where(
                    Team.organization_id == organization_id,
                    Team.id == action.team_id,
                    Team.is_active.is_(True),
                )
            )
            if team is None:
                raise RuntimeError("automation_assignment_team_unavailable")
            member_in_team = False
            if ticket.assignee_id is not None:
                member_in_team = await db.scalar(
                    select(TeamMember.user_id).where(
                        TeamMember.organization_id == organization_id,
                        TeamMember.team_id == team.id,
                        TeamMember.user_id == ticket.assignee_id,
                    )
                ) is not None
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before = {
                "team_id": str(ticket.team_id) if ticket.team_id else None,
                "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            }
            ticket.team_id = team.id
            if not member_in_team:
                ticket.assignee_id = None
            after = {
                "team_id": str(ticket.team_id),
                "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
            }
            if before != after:
                db.add(TicketActivity(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    actor_user_id=None,
                    activity_type="automation_action",
                    details={"action": action.kind, "before": before, "after": after},
                ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied" if before != after else "skipped",
                "detail": f"Ticket routed to {team.name}" if before != after else "Ticket already had this team",
            })
        elif action.kind == "set_ticket_status":
            target = action.value.strip().casefold()
            if target not in SUPPORTED_TICKET_STATUSES:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Unsupported ticket status; use open, pending, resolved, or closed",
                })
                continue
            current_cf = ticket.status.strip().casefold()
            if current_cf == target:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Ticket already had this status",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before = {"status": ticket.status}
            ticket.status = target
            after = {"status": ticket.status}
            db.add(TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=None,
                activity_type="automation_action",
                details={"action": action.kind, "before": before, "after": after},
            ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": "Ticket updated",
            })
        elif action.kind == "set_conversation_ai_mode":
            if conversation.ai_mode == action.mode:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Conversation already in this AI mode",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before_mode = conversation.ai_mode
            conversation.ai_mode = action.mode
            db.add(TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=None,
                activity_type="automation_action",
                details={
                    "action": action.kind,
                    "before": {"conversation_ai_mode": before_mode},
                    "after": {"conversation_ai_mode": conversation.ai_mode},
                },
            ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": "Conversation updated",
            })
        elif action.kind == "route_to_ai_bot":
            if conversation.channel != "shopify_widget":
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Bot routing is available for Shopify storefront widget conversations",
                })
                continue
            target = await db.scalar(
                select(AIAgent)
                .where(
                    AIAgent.organization_id == organization_id,
                    AIAgent.id == action.ai_agent_id,
                    AIAgent.status == "active",
                )
                .with_for_update()
            )
            if target is None:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Selected AI bot is no longer active in this workspace",
                })
                continue
            current = await db.scalar(
                select(Conversation)
                .where(
                    Conversation.organization_id == organization_id,
                    Conversation.id == conversation_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if current is None:
                raise RuntimeError("automation_conversation_unavailable")
            if current.ai_agent_id == target.id and current.ai_agent_override:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Conversation already routes to this AI bot",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before = {
                "ai_agent_id": str(current.ai_agent_id),
                "ai_agent_override": current.ai_agent_override,
            }
            current.ai_agent_id = target.id
            current.ai_agent_override = True
            db.add(TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=None,
                activity_type="automation_action",
                details={
                    "action": action.kind,
                    "before": before,
                    "after": {
                        "ai_agent_id": str(current.ai_agent_id),
                        "ai_agent_name": target.name,
                        "ai_agent_override": True,
                    },
                },
            ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": f"Future widget replies route to {target.name}",
            })
        elif action.kind == "restore_widget_bot_routing":
            if conversation.channel != "shopify_widget":
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Widget bot routing is only available for Shopify storefront conversations",
                })
                continue
            current = await db.scalar(
                select(Conversation)
                .where(
                    Conversation.organization_id == organization_id,
                    Conversation.id == conversation_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if current is None:
                raise RuntimeError("automation_conversation_unavailable")
            if not current.ai_agent_override:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Conversation already uses widget bot routing",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            before = {
                "ai_agent_id": str(current.ai_agent_id),
                "ai_agent_override": True,
            }
            current.ai_agent_override = False
            db.add(TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=None,
                activity_type="automation_action",
                details={
                    "action": action.kind,
                    "before": before,
                    "after": {"ai_agent_override": False},
                },
            ))
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": "Future widget replies use configured multi-bot routing",
            })
        elif action.kind == "add_internal_note":
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            await _append_internal_note(db, organization_id, conversation_id, action.body)
            outcomes.append({
                "action": action.kind,
                "outcome": "applied",
                "detail": "Internal note added",
            })
        elif action.kind == "request_commerce_approval":
            if "shopify.read" not in capabilities:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Shopify not connected",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            outcome, detail, _commerce_id = await request_verified_shopify_cancellation(
                db,
                organization_id,
                ticket_id=ticket.id,
                conversation_id=conversation_id,
                summary=action.summary,
                detail=action.detail,
                order_number_regex=action.order_number_regex,
                message=message_content,
                execution_id=execution_id,
                action_index=index,
                correlation_id=execution.correlation_id,
            )
            if outcome == "applied":
                note_lines = [f"[Commerce approval] {action.summary}", detail]
                if action.detail:
                    note_lines.append(action.detail)
                await _append_internal_note(
                    db, organization_id, conversation_id, "\n".join(note_lines).strip()[:4000]
                )
            outcomes.append({
                "action": action.kind,
                "outcome": outcome,
                "detail": detail,
            })
        elif action.kind == "lookup_shopify_order":
            if "shopify.read" not in capabilities or not shopify_connected:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Shopify not connected",
                })
                continue
            if not customer_email:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Customer email missing for verified lookup",
                })
                continue
            order_guess = extract_order_number(message_content, action.order_number_regex)
            if not order_guess:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "No order number found in message",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            ok, summary = await read_shopify_order_summary(
                db, organization_id, order_number=order_guess, customer_email=customer_email
            )
            body = f"[Shopify order lookup] {summary}" if ok else f"[Shopify order lookup failed] {summary}"
            await _append_internal_note(db, organization_id, conversation_id, body)
            outcomes.append({
                "action": action.kind,
                "outcome": "applied" if ok else "skipped",
                "detail": summary,
            })
        elif action.kind == "search_shopify_catalog":
            if "shopify.read" not in capabilities or not shopify_connected:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Shopify not connected",
                })
                continue
            phrase = extract_catalog_query(message_content, action.query_regex)
            if not phrase:
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "No search phrase derived from message",
                })
                continue
            if not await _claim_effect(db, organization_id, execution_id, effect_key):
                outcomes.append({
                    "action": action.kind,
                    "outcome": "skipped",
                    "detail": "Already applied (idempotent replay)",
                })
                continue
            ok, summary = await read_shopify_catalog_titles(
                db, organization_id, query=phrase, max_results=action.max_results
            )
            body = f"[Shopify catalog] {summary}" if ok else f"[Shopify catalog] {summary}"
            await _append_internal_note(db, organization_id, conversation_id, body[:4000])
            outcomes.append({
                "action": action.kind,
                "outcome": "applied" if ok else "skipped",
                "detail": summary,
            })
        else:
            raise RuntimeError("automation_action_unsupported")
    return [
        {**outcome, "action_index": index}
        for index, outcome in enumerate(outcomes)
    ]
