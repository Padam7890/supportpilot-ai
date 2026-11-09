"""Background execution and tenant-scoped retrieval for AI tasks."""

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.core.config import settings
from app.core.observability import current_correlation_id
from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.catalog_search import (
    catalog_has_active_products,
    load_candidates,
)
from app.features.ai.application.context import load_execution_context
from app.features.ai.application.claim_grounding import check_generated_answer
from app.features.ai.application.conversation_orchestration import (
    plan_playground_turn,
    plan_widget_turn,
    playground_missing_knowledge_reply,
)
from app.features.ai.application.conversational_intents import widget_conversational_reply
from app.features.ai.application.follow_up import (
    VERIFY_REFUND,
    assess_widget_follow_up,
    infer_assistant_question,
    order_verification_question,
)
from app.features.ai.application.intent_extraction import extract_intent
from app.features.ai.application.intent_routing import (
    apply_routing_to_widget_plan,
    resolve_customer_routing,
)
from app.features.ai.application.knowledge_inventory import (
    format_knowledge_inventory,
    is_knowledge_inventory_question,
    load_knowledge_inventory,
)
from app.features.ai.application.retrieval import is_contextual_follow_up
from app.features.ai.application.retrieval_search import citations_remain_authorized
from app.features.ai.application.widget_orders import (
    _question_order_number,
    refund_verification_is_active,
    verified_widget_order_reply,
)
from app.features.ai.application.widget_replies import (
    finish_widget_reply,
    process_widget_shopping_execution,
    widget_reply_is_stale,
)
from app.features.ai.application.widget_stream_context import last_grounded_exchange
from app.features.ai.domain.failure_codes import (
    is_retryable_ai_failure,
)
from app.features.ai.domain.failure_codes import (
    safe_ai_failure_code as _safe_ai_failure_code,
)
from app.features.ai.domain.ranking import build_recommendation_result
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    execution_token_budget,
    provider_configuration_error,
)
from app.features.ai.infrastructure.widget_stream import publish_widget_deltas
from app.features.ai.application.generation_metrics import log_generation_metrics
from app.models import (
    AIAgent,
    AIExecution,
    RecommendationSettings,
)
from app.services.ai_execution import create_grounded_draft
from app.services.widget_ai import (
    AI_TEMPORARY_FAILURE_REPLY,
    ORDER_VERIFICATION_MESSAGE,
    VERIFIED_CANCELLATION_REPLY,
    WIDGET_PROVIDER_UNAVAILABLE_REPLY,
    widget_is_cancellation_request,
    widget_missing_knowledge_reply,
    widget_request_needs_order_verification,
)
from app.workers.domain.lease_policy import AI_EXECUTION_LEASE as LEASE_TIMEOUT
from app.workers.domain.retry_policy import retry_delay_seconds

logger = logging.getLogger(__name__)
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
        execution.playground_history = None
        execution.error_code = "worker_lease_expired"
        if execution.kind == "widget_reply":
            execution.reply_status = "failed"
        execution.safe_summary = (
            "The AI request could not be completed. You can create a new request."
        )
        execution.completed_at = now
        await db.commit()
        return True


async def finish_no_knowledge_execution(
    organization_id: UUID, execution_id: UUID, *, question: str = ""
) -> None:
    """Complete a non-widget run without calling the model when retrieval is empty."""
    await finish_deterministic_ai_execution(
        organization_id,
        execution_id,
        draft=playground_missing_knowledge_reply(question),
        safe_summary=(
            "No matching knowledge was found in the active bot’s assigned sources; no model answer was generated."
        ),
        tool_name="tenant_knowledge_search",
        result_count=0,
    )


async def finish_deterministic_ai_execution(
    organization_id: UUID,
    execution_id: UUID,
    *,
    draft: str,
    safe_summary: str,
    tool_name: str,
    result_count: int,
) -> None:
    """Persist a deterministic AI result without retaining private request context."""
    now = datetime.now(UTC)
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
        row.status = "succeeded"
        row.integration_context_encrypted = None
        row.playground_history = None
        row.draft = draft
        row.safe_summary = safe_summary
        row.citations = []
        row.tool_outcomes = [
            {"tool": tool_name, "status": "completed", "result_count": result_count}
        ]
        row.usage = {}
        row.model_name = None
        row.error_code = None
        row.completed_at = now
        await db.commit()


def _can_stream_transcript(transcript: list[dict[str, str]]) -> bool:
    """Exclude prior staff replies and assistant turns that may contain order facts."""
    previous_social_reply = None
    for turn in transcript:
        sender, content = turn.get("sender"), turn.get("content", "")
        if sender == "customer":
            social = widget_conversational_reply(content)
            previous_social_reply = social[0] if social else None
        elif sender != "assistant" or previous_social_reply != content:
            return False
        else:
            previous_social_reply = None
    return True


def _stream_conversation_context(
    question: str, transcript: list[dict[str, str]],
) -> list[dict[str, str]] | None:
    if _can_stream_transcript(transcript):
        return transcript
    if is_contextual_follow_up(question):
        # A reference can depend on an earlier reply with private order data.
        return None
    # Standalone turns already have the current question and authorized sources.
    # Do not send historical assistant or staff content to a provisional reply.
    return []


async def _process_ai_execution(organization_id: UUID, execution_id: UUID) -> None:
    now = datetime.now(UTC)
    started_at = time.monotonic()
    correlation_id = current_correlation_id()
    execution_kind = "unknown"
    ai_agent_id: UUID | None = None
    attempt_count = 0
    retrieval_match_count: int | None = None
    failure_stage = "context_and_retrieval"
    try:
        loaded = await load_execution_context(organization_id, execution_id)
        if loaded is None:
            _log_ai_execution_event(
                "ai_execution_skipped",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                failure_stage="load_execution",
                execution_status="not_running_or_missing",
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
            )
            return
        execution, question, transcript, context, citations, outcomes, integration_context = loaded
        correlation_id = getattr(execution, "correlation_id", None) or correlation_id
        execution_kind = execution.kind
        ai_agent_id = execution.ai_agent_id
        attempt_count = execution.attempt_count
        retrieval_match_count = len(citations)
        _log_ai_execution_event(
            "ai_execution_started",
            execution_id=str(execution_id),
            correlation_id=correlation_id,
            execution_kind=execution_kind,
            ai_agent_id=str(ai_agent_id) if ai_agent_id else None,
            attempt_count=attempt_count,
            retrieval_match_count=retrieval_match_count,
        )
        failure_stage = "deterministic_routing"
        intent_router_outcome: dict[str, object] | None = None
        if execution.kind == "recommendation":
            allowed_tools = execution.ai_agent_tools_snapshot
            if allowed_tools is None:
                async with SessionLocal() as db:
                    await set_tenant_context(db, organization_id)
                    agent = await db.scalar(
                        select(AIAgent).where(
                            AIAgent.id == execution.ai_agent_id,
                            AIAgent.organization_id == organization_id,
                        )
                    )
                    allowed_tools = list(agent.allowed_tools or []) if agent is not None else []
            if "recommend_products" not in allowed_tools:
                from app.schemas.recommendations import RecommendationResult

                result = RecommendationResult(
                    response_type="unsupported",
                    explanation="Product recommendations are disabled for this AI bot. Contact a workspace administrator if you need them enabled.",
                    available_actions=["refine_search"],
                )
                usage, model_name = {}, None
            else:
                result = None
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                if result is None:
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
                else:
                    candidates, categories, brands = [], [], []
                    catalog_empty = False
                    policy = None
            if result is None and policy is not None and not policy.enabled:
                from app.schemas.recommendations import RecommendationResult

                usage, model_name = {}, None
                result = RecommendationResult(
                    response_type="unsupported",
                    explanation="Product recommendations are currently disabled for this store.",
                    available_actions=["refine_search"],
                )
            elif result is None:
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
                row.playground_history = None
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
        routed_question = execution.question if execution.kind == "widget_reply" else question
        follow_up_query = None
        generic_clarification = None
        if execution.kind == "widget_reply":
            if await widget_reply_is_stale(organization_id, execution_id):
                return
            delivery_status = "draft_ready" if execution.delivery_mode == "draft_only" else "sent"
            follow_up, follow_up_reason = assess_widget_follow_up(
                execution.question, transcript, agent_id=execution.ai_agent_id,
                source_message_id=getattr(execution, "source_message_id", None), now=now,
                allow_refund_workflow=execution.delivery_mode == "auto_reply",
            )
            _log_ai_execution_event(
                "widget_follow_up_routing", execution_id=str(execution_id),
                correlation_id=correlation_id, reason=follow_up_reason,
                decision=follow_up.decision if follow_up else None,
            )
            if follow_up is not None and (follow_up.draft or follow_up.review):
                draft, next_question, reply_status = follow_up.draft, follow_up.pending, delivery_status
                review_citations = []
                safe_summary = "The shopper continued a support workflow."
                if follow_up.handoff:
                    reply_status = "escalated"
                    safe_summary = "The shopper requested support because their order reference was unavailable."
                if review := follow_up.review:
                    failure_stage = "refund_verification"
                    if (
                        review.verification_id and review.item_message_id and review.refund_reason
                        and await refund_verification_is_active(
                            organization_id, execution.conversation_id, review.verification_id
                        )
                    ):
                        failure_stage = "knowledge_retrieval"
                        policy = await load_execution_context(
                            organization_id, execution_id, include_knowledge=True,
                            follow_up_query=f"refund return eligibility policy {review.refund_reason.replace('_', ' ')}",
                        )
                        if policy is None:
                            return
                        review_citations = policy[4]
                        draft = "I’ll send your verified refund request to the store team to check eligibility. No refund has been issued."
                        reply_status = "escalated"
                        safe_summary = "The shopper verified their order and requested staff review for refund eligibility."
                    else:
                        draft = VERIFY_REFUND
                        next_question = review.model_copy(update={
                            "stage": "refund_verification", "expected_answer_type": "otp",
                            "verification_status": "required", "verification_id": None,
                        })
                await finish_widget_reply(
                    organization_id, execution_id, draft=draft or "",
                    reply_status=reply_status,
                    safe_summary=safe_summary,
                    citations=review_citations,
                    outcomes=[{
                        "tool": "widget_follow_up", "status": follow_up.decision,
                        "result_count": len(review_citations),
                    }],
                    usage={}, model_name=None, pending_question=next_question,
                )
                return
            if follow_up is not None and follow_up.routed_question:
                routed_question = follow_up.routed_question
                if follow_up.decision == "policy_timing":
                    follow_up_query = routed_question
                turn = plan_widget_turn(routed_question, transcript)
                intent_router_outcome = {"tool": "widget_follow_up", "status": follow_up.decision}
            else:
                routing = await resolve_customer_routing(
                    routed_question, transcript, channel="widget"
                )
                intent_router_outcome = routing.tool_outcome()
                _log_ai_execution_event(
                    "intent_router_resolved",
                    execution_id=str(execution_id),
                    correlation_id=correlation_id,
                    **{k: intent_router_outcome.get(k) for k in ("mode", "primary_intent", "metrics")},
                )
                turn = apply_routing_to_widget_plan(routed_question, transcript, routing)
            router_outcomes = [intent_router_outcome] if intent_router_outcome else []
            if turn.route == "clarification" and turn.tool_name == "intent_router_clarification":
                generic_clarification = turn.draft
            elif turn.route in {"direct", "purchase", "clarification"}:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=turn.draft or "",
                    reply_status=delivery_status,
                    safe_summary=turn.safe_summary or "",
                    citations=[],
                    outcomes=router_outcomes,
                    usage={},
                    model_name=None,
                )
                return
            if turn.route == "sensitive":
                draft = turn.draft or ""
                reply_status = turn.reply_status
                safe_summary = turn.safe_summary or ""
                pending_order = None
                if widget_is_cancellation_request(routed_question):
                    order_verified, _order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, routed_question
                    )
                    if order_verified:
                        draft = VERIFIED_CANCELLATION_REPLY
                        safe_summary = "A previously verified order cancellation still requires human approval."
                    else:
                        pending_order = order_verification_question(action="cancel")
                elif widget_request_needs_order_verification(routed_question):
                    order_verified, order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, routed_question
                    )
                    if order_verified:
                        draft = order_reply or (
                            "Your order is verified, but I couldn’t retrieve its latest status. "
                            "A store teammate can follow up here."
                        )
                        reply_status = (
                            "escalated"
                            if order_reply is None or "teammate can help" in order_reply.casefold()
                            else delivery_status
                        )
                        safe_summary = "A current Shopify order lookup used the shopper’s active email verification."
                    elif draft == ORDER_VERIFICATION_MESSAGE:
                        pending_order = order_verification_question()
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=draft,
                    reply_status=reply_status,
                    safe_summary=safe_summary,
                    citations=[],
                    outcomes=router_outcomes,
                    usage={},
                    model_name=None,
                    pending_question=pending_order,
                )
                return
            shopping_outcome = not follow_up_query and await process_widget_shopping_execution(
                organization_id, execution_id, question=routed_question
            )
            if shopping_outcome:
                return
            if follow_up is not None and follow_up.decision == "product_reference":
                await finish_widget_reply(
                    organization_id, execution_id,
                    draft="What would you like to know about that option? You can also tell me its name.",
                    reply_status=delivery_status,
                    safe_summary="The shopper referred to a previously displayed product.",
                    citations=[], outcomes=router_outcomes, usage={}, model_name=None,
                )
                return
            failure_stage = "knowledge_retrieval"
            loaded = await load_execution_context(
                organization_id,
                execution_id,
                include_knowledge=True,
                **({"follow_up_query": follow_up_query} if follow_up_query else {}),
            )
            if loaded is None:
                return
            execution, question, transcript, context, citations, outcomes, integration_context = (
                loaded
            )
            if intent_router_outcome:
                outcomes = [intent_router_outcome, *outcomes]
            if follow_up_query:
                question = f"Customer follow-up: {follow_up_query}"
            retrieval_match_count = len(citations)
            _log_ai_execution_event(
                "ai_knowledge_retrieval_completed",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                execution_kind=execution_kind,
                ai_agent_id=str(ai_agent_id) if ai_agent_id else None,
                retrieval_match_count=retrieval_match_count,
            )
        if execution.kind == "playground" and is_knowledge_inventory_question(question):
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                inventory = await load_knowledge_inventory(
                    db,
                    organization_id=organization_id,
                    ai_agent_id=execution.ai_agent_id,
                )
                answer, document_count = format_knowledge_inventory(inventory)
                row = await db.scalar(
                    select(AIExecution)
                    .where(
                        AIExecution.id == execution_id,
                        AIExecution.organization_id == organization_id,
                        AIExecution.kind == "playground",
                        AIExecution.status == "running",
                    )
                    .with_for_update()
                )
                if row is None:
                    await db.rollback()
                    return
                row.status = "succeeded"
                row.playground_history = None
                row.integration_context_encrypted = None
                row.draft = answer
                row.safe_summary = f"Listed {document_count} ready document(s) in this bot’s active assigned sources; no model call was made."
                row.citations = []
                row.tool_outcomes = [
                    {
                        "tool": "knowledge_source_inventory",
                        "status": "completed",
                        "result_count": document_count,
                    }
                ]
                row.usage = {}
                row.model_name = None
                row.error_code = None
                row.completed_at = now
                await db.commit()
            return
        if execution.kind == "playground":
            playground_plan = plan_playground_turn(question, transcript)
            if playground_plan is not None:
                await finish_deterministic_ai_execution(
                    organization_id,
                    execution_id,
                    draft=playground_plan.draft or "",
                    safe_summary=playground_plan.safe_summary or "",
                    tool_name=playground_plan.tool_name,
                    result_count=0,
                )
                return
            routing = await resolve_customer_routing(
                question, transcript or [], channel="playground"
            )
            intent_router_outcome = routing.tool_outcome()
            _log_ai_execution_event(
                "intent_router_resolved",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                channel="playground",
                **{k: intent_router_outcome.get(k) for k in ("mode", "primary_intent", "metrics")},
            )
        if not context and not integration_context:
            if execution.kind == "widget_reply":
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=generic_clarification or widget_missing_knowledge_reply(execution.question),
                    reply_status=delivery_status if generic_clarification else "escalated",
                    safe_summary=(
                        "The shopper was asked for clarification after no matching sources were found."
                        if generic_clarification else
                        "No matching knowledge was found in the active bot’s assigned sources. The shopper received a safe next step."
                    ),
                    citations=[],
                    outcomes=[
                        *([intent_router_outcome] if intent_router_outcome else []),
                        {
                            "tool": "tenant_knowledge_search",
                            "status": "completed",
                            "result_count": 0,
                        },
                    ],
                    usage={},
                    model_name=None,
                )
                return
            await finish_no_knowledge_execution(organization_id, execution_id, question=question)
            return
        if execution.kind == "widget_reply":
            failure_stage = "provider_configuration"
            if error := provider_configuration_error():
                raise error
        failure_stage = "provider_generation"
        draft_inputs = {
            "organization_id": organization_id,
            "execution_id": execution_id,
            "question": question,
            "instructions": execution.instructions,
            "conversation_context": [{"sender": turn["sender"], "content": turn["content"]} for turn in transcript],
            "knowledge_context": context,
            "integration_context": integration_context,
            "auto_reply": (
                execution.kind == "widget_reply" and execution.delivery_mode == "auto_reply"
            ),
        }
        stream_context = None
        stream_source_ids = None
        if (
            settings.widget_ai_streaming_enabled
            and not context  # Never publish unvalidated knowledge-grounded tokens.
            and execution.kind == "widget_reply"
            and execution.delivery_mode == "auto_reply"
            and execution.conversation_id is not None
            and citations
            and not integration_context
            and not follow_up_query
        ):
            stream_context = _stream_conversation_context(execution.question, transcript)
            source_ids = {str(citation["document_id"]) for citation in citations}
            if stream_context is None and (grounded := last_grounded_exchange(transcript)):
                prior_context, prior_sources = grounded
                async with SessionLocal() as db:
                    await set_tenant_context(db, organization_id)
                    authorized = await citations_remain_authorized(
                        db, organization_id=organization_id, ai_agent_id=execution.ai_agent_id,
                        citations=[{"document_id": source_id} for source_id in sorted(prior_sources)],
                    )
                if authorized:
                    stream_context = prior_context
                    source_ids.update(prior_sources)
            if stream_context is not None:
                stream_source_ids = sorted(source_ids)
            _log_ai_execution_event(
                "ai_widget_stream_decision",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                decision="streaming" if stream_context is not None else "context_required",
                historical_context_omitted=stream_context is not None and stream_context != transcript,
            )
        generation_started = time.monotonic()
        if stream_context is not None and stream_source_ids:
            draft_inputs["conversation_context"] = [{"sender": turn["sender"], "content": turn["content"]} for turn in stream_context]
            async with publish_widget_deltas(
                organization_id, execution.conversation_id, execution_id, attempt_count, stream_source_ids
            ) as publish:
                result = await create_grounded_draft(**draft_inputs, on_delta=publish)
        else:
            result = await create_grounded_draft(**draft_inputs)
        log_generation_metrics(
            execution_id=str(execution_id),
            execution_kind=execution.kind,
            model_name=result.get("model_name") if isinstance(result.get("model_name"), str) else None,
            started_monotonic=generation_started,
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else None,
            streamed=stream_context is not None and bool(stream_source_ids),
            correlation_id=correlation_id,
        )
        generated_draft = str(result.get("draft", ""))[:12000]
        grounding_check = check_generated_answer(
            generated_draft, context if not integration_context else []
        )
        if not grounding_check.accepted:
            # Never persist unsupported model-generated numeric claims.
            # Streaming deltas can already have reached the client.
            generated_draft = (
                "I couldn't verify the details in the available knowledge sources. "
                "Please contact our support team to confirm."
            )
            citations = []
            outcomes.append({
                "tool": "claim_grounding",
                "status": "blocked",
                "reason": grounding_check.reason,
            })
        if execution.kind == "widget_reply":
            failure_stage = "reply_persistence"
            draft = generated_draft
            await finish_widget_reply(
                organization_id,
                execution_id,
                draft=draft,
                reply_status="draft_ready" if execution.delivery_mode == "draft_only" else "sent",
                safe_summary=(
                    "Generated answer failed knowledge grounding checks; a safe fallback was used."
                    if not grounding_check.accepted else
                    f"Reply generated using {len(citations)} tenant knowledge source(s)."
                ),
                citations=citations,
                outcomes=outcomes,
                usage=result.get("usage", {}) if isinstance(result.get("usage"), dict) else {},
                model_name=str(result.get("model_name", ""))[:120] or None,
                pending_question=infer_assistant_question(draft),
                stream_source_ids=stream_source_ids,
            )
            return
        async with SessionLocal() as db:
            failure_stage = "result_persistence"
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
            active_agent = await db.scalar(
                select(AIAgent)
                .where(
                    AIAgent.id == row.ai_agent_id,
                    AIAgent.organization_id == organization_id,
                    AIAgent.status == "active",
                )
                .with_for_update()
            )
            if active_agent is None:
                row.status = "succeeded"
                row.integration_context_encrypted = None
                row.playground_history = None
                row.draft = "This AI bot is inactive. Activate it and run the request again."
                row.safe_summary = (
                    "The selected AI bot was deactivated before the answer completed."
                )
                row.citations = []
                row.error_code = None
                row.completed_at = now
                await db.commit()
                return
            if not await citations_remain_authorized(
                db,
                organization_id=organization_id,
                ai_agent_id=row.ai_agent_id,
                citations=citations,
            ):
                row.status = "succeeded"
                row.integration_context_encrypted = None
                row.playground_history = None
                row.draft = (
                    "A knowledge source used for this answer changed before it completed. "
                    "Please run the request again to use the bot’s current sources."
                )
                row.safe_summary = (
                    "A cited knowledge source was removed or changed before this answer completed; "
                    "the generated response was suppressed."
                )
                row.citations = []
                row.error_code = None
                row.completed_at = now
                await db.commit()
                return
            row.status = "succeeded"
            row.integration_context_encrypted = None
            row.playground_history = None
            row.draft = generated_draft
            output_label = "Reply draft" if row.kind == "reply_draft" else "Playground answer"
            row.safe_summary = (
                "Generated answer failed knowledge grounding checks; a safe fallback was used."
                if not grounding_check.accepted else
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
        if failure_stage == "knowledge_retrieval" and failure_code == "ai_execution_failed":
            failure_code = "knowledge_retrieval_failed"
        status_match = re.fullmatch(r"provider_http_(\d{3})", failure_code)
        provider_http_status = (
            exc.http_status if isinstance(exc, AIProviderError) and exc.http_status is not None
            else int(status_match.group(1)) if status_match else None
        )
        provider_reason = exc.provider_reason if isinstance(exc, AIProviderError) else None
        retryable = is_retryable_ai_failure(exc)
        _log_ai_execution_event(
            "ai_execution_failed",
            execution_id=str(execution_id),
            correlation_id=correlation_id,
            execution_kind=execution_kind,
            ai_agent_id=str(ai_agent_id) if ai_agent_id else None,
            failure_stage=failure_stage,
            error_code=failure_code,
            error_type=type(exc).__name__,
            provider_http_status=provider_http_status,
            provider_reason=provider_reason,
            attempt_count=attempt_count,
            retry_count=max(0, attempt_count - 1),
            elapsed_ms=round((time.monotonic() - started_at) * 1000),
            retrieval_match_count=retrieval_match_count,
            retryable=retryable,
        )
        widget_needs_fallback = False
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
            attempt_count = row.attempt_count
            exhausted = not retryable or attempt_count >= row.max_attempts
            _log_ai_execution_event(
                "ai_execution_retry_decision",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                failure_stage=failure_stage,
                error_code=failure_code,
                provider_http_status=provider_http_status,
                provider_reason=provider_reason,
                attempt_count=attempt_count,
                retry_count=max(0, attempt_count - 1),
                max_attempts=row.max_attempts,
                elapsed_ms=round((time.monotonic() - started_at) * 1000),
                decision="retry_scheduled" if not exhausted else (
                    "retry_exhausted" if retryable else "not_retryable"
                ),
            )
            if exhausted and row.kind == "widget_reply":
                widget_needs_fallback = True
                await db.rollback()
            else:
                row.status = "failed" if exhausted else "queued"
                if row.kind == "widget_reply":
                    row.reply_status = "failed" if exhausted else "processing"
                if exhausted:
                    row.integration_context_encrypted = None
                    row.playground_history = None
                row.error_code = failure_code
                row.safe_summary = (
                    "The AI request could not be completed. You can create a new request."
                    if exhausted
                    else None
                )
                if not exhausted:
                    row.next_attempt_at = now + timedelta(
                        seconds=retry_delay_seconds(attempt_count, base_seconds=5, cap_seconds=60)
                    )
                row.completed_at = now if exhausted else None
                await db.commit()
        if widget_needs_fallback:
            try:
                provider_failed = (
                    failure_stage in {"provider_configuration", "provider_generation"}
                    and isinstance(exc, AIProviderError)
                )
                fallback_draft = (
                    WIDGET_PROVIDER_UNAVAILABLE_REPLY
                    if provider_failed and retrieval_match_count
                    else AI_TEMPORARY_FAILURE_REPLY
                )
                summary = {
                    "provider_configuration": "Chat provider configuration prevented generation.",
                    "provider_generation": "AI generation could not complete.",
                    "knowledge_retrieval": "Knowledge retrieval could not complete.",
                    "reply_persistence": "The generated reply could not be saved.",
                }.get(failure_stage, "AI reply processing could not complete.")
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=fallback_draft,
                    reply_status="escalated",
                    safe_summary=summary + " A safe handoff reply was prepared.",
                    citations=citations if failure_stage == "provider_configuration" else [],
                    outcomes=outcomes if failure_stage == "provider_configuration" else [],
                    usage={},
                    model_name=None,
                    failure_code=failure_code,
                )
            except Exception as fallback_exc:  # noqa: BLE001 - keep the worker alive if persistence is unavailable.
                _log_ai_execution_event(
                    "ai_widget_fallback_persistence_failed",
                    execution_id=str(execution_id),
                    correlation_id=correlation_id,
                    execution_kind=execution_kind,
                    ai_agent_id=str(ai_agent_id) if ai_agent_id else None,
                    failure_stage="fallback_persistence",
                    error_code=_safe_ai_failure_code(fallback_exc),
                    error_type=type(fallback_exc).__name__,
                    provider_http_status=None,
                    attempt_count=attempt_count,
                    elapsed_ms=round((time.monotonic() - started_at) * 1000),
                    retrieval_match_count=retrieval_match_count,
                    execution_status="failed",
                    delivery_status="failed",
                )


def _log_ai_execution_event(event: str, **fields: object) -> None:
    """Emit one JSON diagnostic record without prompt, customer, or credential data."""
    logger.info("ai_execution_event %s", json.dumps({"event": event, **fields}, sort_keys=True))


async def process_ai_execution(organization_id: UUID, execution_id: UUID) -> None:
    """Execute under an aggregate per-job model-call and token budget."""
    with execution_token_budget():
        await _process_ai_execution(organization_id, execution_id)
