"""Background execution and tenant-scoped retrieval for AI tasks."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.catalog_search import (
    catalog_has_active_products,
    load_candidates,
)
from app.features.ai.application.context import load_execution_context
from app.features.ai.application.intent_extraction import extract_intent
from app.features.ai.application.widget_orders import (
    _question_order_number,
    verified_widget_order_reply,
)
from app.features.ai.application.widget_replies import (
    finish_widget_reply,
    process_widget_shopping_execution,
    widget_reply_is_stale,
)
from app.features.ai.domain.failure_codes import safe_ai_failure_code as _safe_ai_failure_code
from app.features.ai.domain.ranking import build_recommendation_result
from app.features.ai.infrastructure.llm_gateway import execution_token_budget
from app.models import (
    AIExecution,
    RecommendationSettings,
)
from app.services.ai_execution import create_grounded_draft, is_provider_configured
from app.services.widget_ai import (
    AI_TEMPORARY_FAILURE_REPLY,
    VERIFIED_CANCELLATION_REPLY,
    widget_clarification_reply,
    widget_greeting_reply,
    widget_is_cancellation_request,
    widget_missing_knowledge_reply,
    widget_purchase_reply,
    widget_request_needs_order_verification,
    widget_sensitive_reply,
)
from app.workers.domain.retry_policy import retry_delay_seconds

logger = logging.getLogger(__name__)
LEASE_TIMEOUT = timedelta(minutes=3)
__all__ = ["_question_order_number", "_safe_ai_failure_code"]


async def claim_ai_execution(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.attempt_count < AIExecution.max_attempts,
                or_(
                    and_(AIExecution.status == "queued", AIExecution.next_attempt_at <= now),
                    and_(
                        AIExecution.status == "running",
                        AIExecution.updated_at <= now - LEASE_TIMEOUT,
                    ),
                ),
            )
            .order_by(AIExecution.created_at, AIExecution.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return None
        execution.status = "running"
        execution.attempt_count += 1
        execution.started_at = now
        execution.error_code = None
        execution_id = execution.id
        await db.commit()
        return execution_id


async def fail_exhausted_ai_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.status == "running",
                AIExecution.attempt_count >= AIExecution.max_attempts,
                AIExecution.updated_at <= now - LEASE_TIMEOUT,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return False
        execution.status = "failed"
        execution.integration_context_encrypted = None
        execution.error_code = "worker_lease_expired"
        if execution.kind == "widget_reply":
            execution.reply_status = "failed"
        execution.safe_summary = (
            "The AI request could not be completed. You can create a new request."
        )
        execution.completed_at = now
        await db.commit()
        return True


async def _process_ai_execution(organization_id: UUID, execution_id: UUID) -> None:
    now = datetime.now(UTC)
    try:
        loaded = await load_execution_context(organization_id, execution_id)
        if loaded is None:
            return
        execution, question, transcript, context, citations, outcomes, integration_context = loaded
        if execution.kind == "recommendation":
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                candidates, categories, brands = await load_candidates(
                    db, organization_id, question
                )
                catalog_empty = (
                    not await catalog_has_active_products(db, organization_id)
                    if not candidates
                    else False
                )
                policy = await db.scalar(
                    select(RecommendationSettings).where(
                        RecommendationSettings.organization_id == organization_id
                    )
                )
            if policy is not None and not policy.enabled:
                from app.schemas.recommendations import RecommendationResult

                usage, model_name = {}, None
                result = RecommendationResult(
                    response_type="unsupported",
                    explanation="Product recommendations are currently disabled for this store.",
                    available_actions=["refine_search"],
                )
            else:
                intent, usage, model_name = await extract_intent(question, categories, brands)
                excluded_ids: set[UUID] = set()
                if policy is not None:
                    for value in policy.excluded_product_ids:
                        try:
                            excluded_ids.add(UUID(value))
                        except (TypeError, ValueError):
                            continue
                    excluded_collections = set(policy.excluded_collection_ids)
                    candidates = [
                        item
                        for item in candidates
                        if item.product.id not in excluded_ids
                        and (not policy.in_stock_only or item.variant.availability == "available")
                        and not (
                            excluded_collections
                            & {
                                str(value)
                                for value in item.product.specifications.get("collection_ids", [])
                            }
                        )
                    ]
                    intent.result_count = min(intent.result_count, policy.max_products)
                result = build_recommendation_result(
                    question,
                    intent,
                    candidates,
                    ranking_preferences=policy.ranking_preferences if policy else None,
                    catalog_empty=catalog_empty,
                )
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                row = await db.scalar(
                    select(AIExecution)
                    .where(
                        AIExecution.id == execution_id,
                        AIExecution.organization_id == organization_id,
                        AIExecution.kind == "recommendation",
                        AIExecution.status == "running",
                    )
                    .with_for_update()
                )
                if row is None:
                    await db.rollback()
                    return
                row.status = "succeeded"
                row.recommendation_result = result.model_dump(mode="json")
                row.safe_summary = (
                    f"Recommendation request completed with {len(result.products)} result(s)."
                )
                row.usage = usage
                row.model_name = model_name
                row.error_code = None
                row.completed_at = now
                await db.commit()
            return
        if execution.kind == "widget_reply":
            if await widget_reply_is_stale(organization_id, execution_id):
                return
            delivery_status = "draft_ready" if execution.delivery_mode == "draft_only" else "sent"
            purchase_reply = widget_purchase_reply(execution.question)
            if purchase_reply is not None:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=purchase_reply,
                    reply_status=delivery_status,
                    safe_summary="The shopper asked to place an order and was directed to the merchant’s checkout; no purchase was created.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            sensitive_reply = widget_sensitive_reply(execution.question)
            if sensitive_reply is not None:
                draft, safe_summary = sensitive_reply
                reply_status = "escalated"
                if widget_is_cancellation_request(execution.question):
                    order_verified, _order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, execution.question
                    )
                    if order_verified:
                        draft = VERIFIED_CANCELLATION_REPLY
                        safe_summary = "A previously verified order cancellation still requires human approval."
                elif widget_request_needs_order_verification(execution.question):
                    order_verified, order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, execution.question
                    )
                    if order_verified:
                        draft = order_reply or AI_TEMPORARY_FAILURE_REPLY
                        reply_status = (
                            "escalated" if draft == AI_TEMPORARY_FAILURE_REPLY else delivery_status
                        )
                        safe_summary = "A current Shopify order lookup used the shopper’s active email verification."
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=draft,
                    reply_status=reply_status,
                    safe_summary=safe_summary,
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            greeting = widget_greeting_reply(execution.question)
            if greeting is not None:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=greeting,
                    reply_status=delivery_status,
                    safe_summary="A conversational reply was prepared without using private customer or order data.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            clarification = widget_clarification_reply(execution.question, transcript)
            if clarification is not None:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=clarification,
                    reply_status=delivery_status,
                    safe_summary="A deterministic clarification explained the active support workflow without a model call.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            shopping_outcome = await process_widget_shopping_execution(
                organization_id, execution_id, question=execution.question
            )
            if shopping_outcome:
                return
            if not context:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=widget_missing_knowledge_reply(execution.question),
                    reply_status="escalated",
                    safe_summary="No matching tenant knowledge was found. The shopper received a clear next step without unsupported claims.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            if not is_provider_configured():
                logger.warning(
                    "Widget AI provider is not configured: execution_id=%s", execution_id
                )
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=AI_TEMPORARY_FAILURE_REPLY,
                    reply_status="escalated",
                    safe_summary="The AI provider is unavailable. A safe handoff reply was prepared.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
        result = await create_grounded_draft(
            organization_id=organization_id,
            execution_id=execution_id,
            question=question,
            instructions=execution.instructions,
            conversation_context=transcript,
            knowledge_context=context,
            integration_context=integration_context,
            auto_reply=(
                execution.kind == "widget_reply" and execution.delivery_mode == "auto_reply"
            ),
        )
        if execution.kind == "widget_reply":
            await finish_widget_reply(
                organization_id,
                execution_id,
                draft=str(result.get("draft", ""))[:12000],
                reply_status="draft_ready" if execution.delivery_mode == "draft_only" else "sent",
                safe_summary=f"Reply grounded in {len(citations)} tenant knowledge source(s).",
                citations=citations,
                outcomes=outcomes,
                usage=result.get("usage", {}) if isinstance(result.get("usage"), dict) else {},
                model_name=str(result.get("model_name", ""))[:120] or None,
            )
            return
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            row = await db.scalar(
                select(AIExecution).where(
                    AIExecution.id == execution_id,
                    AIExecution.organization_id == organization_id,
                    AIExecution.status == "running",
                )
            )
            if row is None:
                await db.rollback()
                return
            row.status = "succeeded"
            row.integration_context_encrypted = None
            row.draft = str(result.get("draft", ""))[:12000]
            output_label = "Reply draft" if row.kind == "reply_draft" else "Playground answer"
            row.safe_summary = (
                f"{output_label} generated using {len(citations)} knowledge source(s)."
            )
            row.citations = citations
            row.tool_outcomes = outcomes
            raw_usage = result.get("usage", {})
            row.usage = raw_usage if isinstance(raw_usage, dict) else {}
            row.model_name = str(result.get("model_name", ""))[:120] or None
            row.error_code = None
            row.completed_at = now
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - record failures safely and keep the worker alive
        failure_code = _safe_ai_failure_code(exc)
        logger.warning(
            "AI execution failed: execution_id=%s error_type=%s failure_code=%s",
            execution_id,
            type(exc).__name__,
            failure_code,
        )
        widget_fallback_mode: str | None = None
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            row = await db.scalar(
                select(AIExecution)
                .where(
                    AIExecution.id == execution_id,
                    AIExecution.organization_id == organization_id,
                    AIExecution.status == "running",
                )
                .with_for_update()
            )
            if row is None:
                await db.rollback()
                return
            exhausted = row.attempt_count >= row.max_attempts
            if exhausted and row.kind == "widget_reply":
                widget_fallback_mode = row.delivery_mode
                await db.rollback()
            else:
                row.status = "failed" if exhausted else "queued"
                if row.kind == "widget_reply":
                    row.reply_status = "failed" if exhausted else "processing"
                if exhausted:
                    row.integration_context_encrypted = None
                row.error_code = failure_code
                row.safe_summary = (
                    "The AI request could not be completed. You can create a new request."
                    if exhausted
                    else None
                )
                row.next_attempt_at = now + timedelta(
                    seconds=retry_delay_seconds(row.attempt_count, base_seconds=5, cap_seconds=60)
                )
                row.completed_at = now if exhausted else None
                await db.commit()
        if widget_fallback_mode is not None:
            try:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=AI_TEMPORARY_FAILURE_REPLY,
                    reply_status="escalated",
                    safe_summary="AI generation failed after its retry limit. A safe handoff reply was prepared.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
            except Exception as fallback_exc:  # noqa: BLE001 - keep the worker alive if persistence is unavailable.
                logger.error(
                    "AI widget fallback persistence failed: execution_id=%s error_type=%s",
                    execution_id,
                    type(fallback_exc).__name__,
                )


async def process_ai_execution(organization_id: UUID, execution_id: UUID) -> None:
    """Execute under an aggregate per-job model-call and token budget."""
    with execution_token_budget():
        await _process_ai_execution(organization_id, execution_id)
