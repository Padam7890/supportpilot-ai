"""Background execution and tenant-scoped retrieval for AI tasks."""

import json
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.observability import current_correlation_id
from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.catalog_conversation import (
    answer_catalog_follow_up, remember_catalog,
)
from app.features.ai.application.catalog_discovery import (
    list_verified_products, render_product_listing, resolve_catalog_connection,
)
from app.features.ai.application.catalog_search import (
    catalog_has_active_products,
    load_candidates,
)
from app.features.ai.application.context import load_execution_context
from app.features.ai.application.execution_failure_persistence import persist_execution_failure
from app.features.ai.application.execution_failure_policy import (
    assess_execution_failure,
)
from app.features.ai.application.execution_lifecycle import (
    claim_ai_execution,
    fail_exhausted_ai_leases,
    finish_deterministic_ai_execution,
)
from app.features.ai.application.follow_up import (
    assess_widget_follow_up,
    infer_assistant_question,
)
from app.features.ai.application.generated_reply_persistence import (
    complete_non_widget_generated_reply,
)
from app.features.ai.application.guarded_generation import generate_guarded_draft
from app.features.ai.application.intent_extraction import extract_intent
from app.features.ai.application.intent_routing import resolve_customer_routing
from app.features.ai.application.knowledge_inventory import is_knowledge_inventory_question
from app.features.ai.application.missing_evidence_policy import plan_missing_evidence_reply
from app.features.ai.application.playground_execution import complete_playground_knowledge_inventory
from app.features.ai.application.playground_routing import route_playground_conversation
from app.features.ai.application.stream_context_policy import (
    can_stream_transcript as _can_stream_transcript,
)
from app.features.ai.application.stream_context_policy import (
    stream_conversation_context as _stream_conversation_context,
)
from app.features.ai.application.widget_failure_fallback import plan_widget_failure_fallback
from app.features.ai.application.widget_follow_up_execution import complete_widget_follow_up
from app.features.ai.application.widget_orders import _question_order_number
from app.features.ai.application.widget_replies import (
    finish_widget_reply,
    process_widget_shopping_execution,
    widget_reply_is_stale,
)
from app.features.ai.application.widget_sensitive_execution import complete_sensitive_widget_turn
from app.features.ai.application.widget_turn_routing import resolve_widget_turn
from app.features.ai.domain.failure_codes import (
    safe_ai_failure_code as _safe_ai_failure_code,
)
from app.features.ai.domain.ranking import build_recommendation_result
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    execution_token_budget,
    provider_configuration_error,
)
from app.models import (
    AIAgent,
    AIExecution,
    RecommendationSettings,
)
from app.services.widget_ai import (
    AI_TEMPORARY_FAILURE_REPLY,
    WIDGET_PROVIDER_UNAVAILABLE_REPLY,
)

logger = logging.getLogger(__name__)
__all__ = [
    "_can_stream_transcript",
    "_question_order_number",
    "_safe_ai_failure_code",
    "_stream_conversation_context",
    "claim_ai_execution",
    "fail_exhausted_ai_leases",
    "finish_deterministic_ai_execution",
    "finish_no_knowledge_execution",
    "process_ai_execution",
]


async def finish_no_knowledge_execution(
    organization_id: UUID, execution_id: UUID, *, question: str = ""
) -> None:
    """Complete a non-widget run without calling the model when retrieval is empty."""
    missing = plan_missing_evidence_reply(
        execution_kind="playground",
        question=question,
    )
    await finish_deterministic_ai_execution(
        organization_id,
        execution_id,
        draft=missing.draft,
        safe_summary=missing.safe_summary,
        tool_name="tenant_knowledge_search",
        result_count=0,
    )


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
        loaded = await load_execution_context(organization_id, execution_id, include_knowledge=False)
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
        requires_store_evidence = True
        if execution.kind == "widget_reply":
            if await widget_reply_is_stale(organization_id, execution_id):
                return
            delivery_status = "draft_ready" if execution.delivery_mode == "draft_only" else "sent"
            # Explicit catalog browsing is a new intent, never an answer to a
            # previous product-selection question. Prevent stale follow-up state
            # from swallowing repeated "list all products" requests.
            from app.features.ai.application.catalog_discovery import is_catalog_discovery_request
            if is_catalog_discovery_request(execution.question):
                follow_up, follow_up_reason = None, "catalog_browse_override"
            else:
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
            if follow_up is not None:
                # Mark the stage before awaiting so thrown retrieval errors are
                # classified correctly without changing their retryable type.
                if follow_up.review is not None:
                    failure_stage = "knowledge_retrieval"
                completion = await complete_widget_follow_up(
                    organization_id,
                    execution_id,
                    execution.conversation_id,
                    follow_up=follow_up,
                    delivery_status=delivery_status,
                )
                if completion.failure_stage is not None:
                    failure_stage = completion.failure_stage
                if completion.completed:
                    return
            if follow_up is not None and follow_up.routed_question:
                routed_question = follow_up.routed_question
                if follow_up.decision == "policy_timing":
                    follow_up_query = routed_question
            route_result = await resolve_widget_turn(
                routed_question,
                transcript,
                follow_up_decision=(
                    follow_up.decision
                    if follow_up is not None and follow_up.routed_question else None
                ),
            )
            turn = route_result.turn
            from app.features.ai.application.catalog_trace import trace_catalog_route
            trace_catalog_route(
                execution_id=str(execution_id), route=turn.route,
                tool=turn.tool_name, follow_up=follow_up_reason,
                catalog_request=is_catalog_discovery_request(execution.question),
            )
            requires_store_evidence = route_result.requires_evidence
            intent_router_outcome = route_result.outcome
            if route_result.model_router_invoked:
                _log_ai_execution_event(
                    "intent_router_resolved",
                    execution_id=str(execution_id),
                    correlation_id=correlation_id,
                    **{k: intent_router_outcome.get(k) for k in ("mode", "primary_intent", "metrics")},
                )
            router_outcomes = [intent_router_outcome] if intent_router_outcome else []
            # Resolve product references against the last authorized catalog page
            # before falling through to generic RAG or clarification.
            if turn.route in {"knowledge", "clarification"} and execution.conversation_id:
                async with SessionLocal() as db:
                    await set_tenant_context(db, organization_id)
                    from app.models import Conversation
                    conversation = await db.scalar(
                        select(Conversation).where(
                            Conversation.id == execution.conversation_id,
                            Conversation.organization_id == organization_id,
                        )
                    )
                    if conversation is not None:
                        connection_id = await resolve_catalog_connection(
                            db, organization_id,
                            bound_connection_id=conversation.integration_connection_id,
                        )
                        catalog_answer = (
                            await answer_catalog_follow_up(
                                db, conversation, organization_id,
                                connection_id, execution.question,
                            )
                            if connection_id is not None else None
                        )
                    else:
                        catalog_answer = None
                if catalog_answer is not None:
                    trace_catalog_route(
                        execution_id=str(execution_id), route="catalog_follow_up",
                        tool="catalog_conversation", follow_up=follow_up_reason,
                        catalog_request=False, connection_resolved=True,
                    )
                    await finish_widget_reply(
                        organization_id, execution_id, draft=catalog_answer,
                        reply_status=delivery_status,
                        safe_summary="Verified catalog follow-up resolved from store-bound context.",
                        citations=[],
                        outcomes=[{"tool": "catalog_conversation", "status": "completed"}],
                        usage={}, model_name=None,
                    )
                    return
            if turn.route == "inventory":
                async with SessionLocal() as db:
                    await set_tenant_context(db, organization_id)
                    from app.models import Conversation
                    conversation = await db.scalar(
                        select(Conversation).where(
                            Conversation.id == execution.conversation_id,
                            Conversation.organization_id == organization_id,
                        )
                    ) if execution.conversation_id else None
                    connection_id = await resolve_catalog_connection(
                        db, organization_id,
                        bound_connection_id=(
                            conversation.integration_connection_id if conversation else None
                        ),
                    )
                    products = (
                        await list_verified_products(
                            db, organization_id, connection_id=connection_id,
                        )
                        if connection_id is not None else []
                    )
                    if conversation is not None and connection_id is not None and products:
                        remember_catalog(conversation, products, connection_id)
                        await db.commit()
                trace_catalog_route(
                    execution_id=str(execution_id), route="inventory_result",
                    tool="catalog_discovery", follow_up=follow_up_reason,
                    catalog_request=True, result_count=len(products),
                    connection_resolved=connection_id is not None,
                )
                draft = (
                    render_product_listing(products) if connection_id is not None
                    else "I can't identify a single connected store for this chat. Please contact the store team."
                )
                await finish_widget_reply(
                    organization_id, execution_id, draft=draft,
                    reply_status=delivery_status,
                    safe_summary="Product listing resolved from an authorized connected catalog.",
                    citations=[],
                    outcomes=[{"tool": "catalog_discovery", "status": "completed",
                               "result_count": len(products)}],
                    usage={}, model_name=None,
                )
                return
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
                await complete_sensitive_widget_turn(
                    organization_id,
                    execution_id,
                    execution.conversation_id,
                    question=routed_question,
                    turn=turn,
                    delivery_status=delivery_status,
                    outcomes=router_outcomes,
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
        if execution.kind == "playground" and is_knowledge_inventory_question(question):
            await complete_playground_knowledge_inventory(
                organization_id,
                execution_id,
                ai_agent_id=execution.ai_agent_id,
            )
            return
        if execution.kind == "playground":
            playground_routing = await route_playground_conversation(
                organization_id,
                execution_id,
                question=question,
                transcript=transcript,
            )
            if playground_routing.completed:
                return
            intent_router_outcome = playground_routing.outcome
            requires_store_evidence = playground_routing.requires_evidence
            _log_ai_execution_event(
                "intent_router_resolved",
                execution_id=str(execution_id),
                correlation_id=correlation_id,
                channel="playground",
                **{k: (intent_router_outcome or {}).get(k) for k in ("mode", "primary_intent", "metrics")},
            )
        if execution.kind == "reply_draft":
            routing = await resolve_customer_routing(
                question, transcript, channel="reply_draft", for_generation=True,
                allow_model=not integration_context,
            )
            # An authorized snapshot answers order status deterministically.
            # Independently retrieve policy evidence for mixed support drafts.
            requires_store_evidence = (
                routing.deterministic.requires_knowledge if integration_context
                else routing.requires_evidence
            )
            intent_router_outcome = routing.tool_outcome()
        if requires_store_evidence:
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
        elif intent_router_outcome:
            outcomes = [intent_router_outcome, *outcomes]
        if requires_store_evidence and not context and not integration_context:
            missing = plan_missing_evidence_reply(
                execution_kind=execution.kind,
                question=execution.question if execution.kind == "widget_reply" else question,
                clarification=generic_clarification,
                intent_router_outcome=intent_router_outcome,
                delivery_status=delivery_status if execution.kind == "widget_reply" else "sent",
            )
            if execution.kind == "widget_reply":
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=missing.draft,
                    reply_status=missing.reply_status,
                    safe_summary=missing.safe_summary,
                    citations=[],
                    outcomes=missing.outcomes,
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
        guarded = await generate_guarded_draft(
            execution_id=str(execution_id),
            execution_kind=execution.kind,
            question=question,
            instructions=execution.instructions,
            transcript=transcript,
            context=context,
            integration_context=integration_context,
            citations=citations,
            outcomes=outcomes,
            requires_evidence=requires_store_evidence,
            correlation_id=correlation_id,
        )
        generated_draft = guarded.text
        citations = guarded.citations
        outcomes = guarded.outcomes
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
                    if not guarded.accepted else
                    f"Reply generated using {len(citations)} tenant knowledge source(s)."
                ),
                citations=citations,
                outcomes=outcomes,
                usage=guarded.usage,
                model_name=guarded.model_name,
                pending_question=infer_assistant_question(draft),
            )
            return
        failure_stage = "result_persistence"
        await complete_non_widget_generated_reply(
            organization_id,
            execution_id,
            guarded=guarded,
            completed_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - record failures safely and keep the worker alive
        # Application errors may carry a precise, allowlisted failure stage.
        # Never trust arbitrary exception text as a diagnostic stage.
        declared_stage = getattr(exc, "failure_stage", None)
        if declared_stage in {"knowledge_retrieval", "refund_verification"}:
            failure_stage = declared_stage
        failure = assess_execution_failure(exc, failure_stage)
        failure_code = failure.code
        provider_http_status = failure.http_status
        provider_reason = failure.provider_reason
        retryable = failure.retryable
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
        transition = await persist_execution_failure(
            organization_id,
            execution_id,
            retryable=retryable,
            failure_code=failure_code,
            now=now,
        )
        if not transition.found:
            return
        attempt_count = transition.attempt_count
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
            max_attempts=transition.max_attempts,
            elapsed_ms=round((time.monotonic() - started_at) * 1000),
            decision=transition.reason,
        )
        widget_needs_fallback = transition.widget_needs_fallback
        if widget_needs_fallback:
            try:
                provider_failed = (
                    failure_stage in {"provider_configuration", "provider_generation"}
                    and isinstance(exc, AIProviderError)
                )
                fallback = plan_widget_failure_fallback(
                    failure_stage=failure_stage,
                    provider_failed=provider_failed,
                    retrieval_match_count=retrieval_match_count,
                    provider_unavailable_reply=WIDGET_PROVIDER_UNAVAILABLE_REPLY,
                    temporary_failure_reply=AI_TEMPORARY_FAILURE_REPLY,
                )
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=fallback.draft,
                    reply_status="escalated",
                    safe_summary=fallback.safe_summary,
                    citations=citations if fallback.retain_retrieval_evidence else [],
                    outcomes=outcomes if fallback.retain_retrieval_evidence else [],
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
