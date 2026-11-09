"""Tenant- and bot-scoped hybrid retrieval shared by AI runs and diagnostics."""

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.ai.application.retrieval import build_retrieval_terms
from app.features.ai.infrastructure.embedding_gateway import (
    EmbeddingProviderError,
    embed_texts,
    is_embedding_provider_configured,
)
from app.models import (
    AIAgent,
    AIAgentKnowledgeBase,
    DocumentChunk,
    DocumentEmbedding,
    KnowledgeBase,
    KnowledgeDocument,
)
from app.models.knowledge_document import Vector

logger = logging.getLogger(__name__)
RRF_K = 60


def reciprocal_rank_fusion(
    keyword_rank: int | None,
    semantic_rank: int | None,
    *,
    k: int = RRF_K,
) -> float:
    """Return the standard RRF score for one-based candidate ranks."""
    if k < 1 or any(rank is not None and rank < 1 for rank in (keyword_rank, semantic_rank)):
        raise ValueError("RRF requires positive ranks and a positive smoothing constant")
    return sum(1 / (k + rank) for rank in (keyword_rank, semantic_rank) if rank is not None)


@dataclass(frozen=True)
class KnowledgeMatch:
    document_id: UUID
    document_name: str
    knowledge_base_name: str
    chunk_index: int
    excerpt: str
    match_basis: str
    rrf_score: float
    semantic_similarity: float | None
    keyword_rank: int | None
    semantic_rank: int | None


@dataclass(frozen=True)
class KnowledgeSearchResult:
    active_assigned_base_count: int
    ready_document_count: int
    terms_available: bool
    matches: list[KnowledgeMatch]
    retrieval_method: str = "none"
    retrieval_latency_ms: int = 0
    embedding_status: str = "disabled"


async def search_agent_knowledge(
    db: AsyncSession,
    *,
    organization_id: UUID,
    ai_agent_id: UUID,
    search_text: str,
    limit: int = 6,
) -> KnowledgeSearchResult:
    """RRF merge lexical and semantic candidates after tenant/bot source filtering."""
    started = time.monotonic()
    assigned_bases = (
        select(AIAgentKnowledgeBase.knowledge_base_id)
        .join(AIAgent, (AIAgent.organization_id == AIAgentKnowledgeBase.organization_id)
              & (AIAgent.id == AIAgentKnowledgeBase.ai_agent_id))
        .join(KnowledgeBase, (KnowledgeBase.organization_id == AIAgentKnowledgeBase.organization_id)
              & (KnowledgeBase.id == AIAgentKnowledgeBase.knowledge_base_id))
        .where(AIAgentKnowledgeBase.organization_id == organization_id,
               AIAgentKnowledgeBase.ai_agent_id == ai_agent_id,
               AIAgent.status == "active", KnowledgeBase.status == "active")
    )
    base_count, document_count = (await db.execute(
        select(func.count(func.distinct(KnowledgeBase.id)),
               func.count(func.distinct(KnowledgeDocument.id)))
        .join(AIAgentKnowledgeBase,
              (AIAgentKnowledgeBase.organization_id == KnowledgeBase.organization_id)
              & (AIAgentKnowledgeBase.knowledge_base_id == KnowledgeBase.id)
              & (AIAgentKnowledgeBase.ai_agent_id == ai_agent_id))
        .join(AIAgent, (AIAgent.organization_id == AIAgentKnowledgeBase.organization_id)
              & (AIAgent.id == AIAgentKnowledgeBase.ai_agent_id)
              & (AIAgent.status == "active"))
        .outerjoin(KnowledgeDocument,
                   (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
                   & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                   & (KnowledgeDocument.status == "ready")
                   & KnowledgeDocument.deleted_at.is_(None))
        .where(KnowledgeBase.organization_id == organization_id,
               KnowledgeBase.status == "active",
               AIAgentKnowledgeBase.organization_id == organization_id)
    )).one()
    terms = build_retrieval_terms(search_text)
    keyword_limit = min(settings.ai_retrieval_keyword_limit, 50)
    semantic_limit = min(settings.ai_retrieval_semantic_limit, 50)
    result_limit = min(max(1, limit), settings.ai_retrieval_result_limit, 10)
    common_filters = (
        DocumentChunk.organization_id == organization_id,
        KnowledgeDocument.organization_id == organization_id,
        KnowledgeDocument.status == "ready",
        KnowledgeDocument.deleted_at.is_(None),
        KnowledgeDocument.knowledge_base_id.in_(assigned_bases),
        KnowledgeBase.organization_id == organization_id,
        KnowledgeBase.status == "active",
    )
    source_query = (
        select(
               DocumentChunk.document_id,
               KnowledgeDocument.name.label("document_name"),
               KnowledgeBase.name.label("knowledge_base_name"),
               DocumentChunk.chunk_index, DocumentChunk.content)
        .join(KnowledgeDocument,
              (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
              & (KnowledgeDocument.id == DocumentChunk.document_id))
        .join(KnowledgeBase,
              (KnowledgeBase.organization_id == KnowledgeDocument.organization_id)
              & (KnowledgeBase.id == KnowledgeDocument.knowledge_base_id))
        .where(*common_filters)
    )
    keyword_rows = []
    if terms:
        simple_config = literal_column("'simple'::regconfig")
        ts_query = func.to_tsquery(simple_config, " | ".join(terms))
        content_vector = func.to_tsvector(simple_config, DocumentChunk.content)
        document_vector = func.to_tsvector(simple_config, KnowledgeDocument.name)
        base_vector = func.to_tsvector(simple_config, KnowledgeBase.name)
        search_vector = (
            func.setweight(document_vector, literal_column("'A'::\"char\""))
            .op("||")(func.setweight(base_vector, literal_column("'B'::\"char\"")))
            .op("||")(func.setweight(content_vector, literal_column("'C'::\"char\"")))
        )
        rank = func.ts_rank_cd(search_vector, ts_query)
        keyword_rows = list((await db.execute(
            source_query.add_columns(literal("chunk_content").label("match_basis"), rank.label("rank"))
            .where(content_vector.op("@@")(ts_query))
            .order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(keyword_limit)
        )).all())
        if len(keyword_rows) < keyword_limit:
            seen = {row.document_id for row in keyword_rows}
            keyword_rows.extend((await db.execute(
                source_query.add_columns(literal("source_title").label("match_basis"), rank.label("rank"))
                .where((document_vector.op("@@")(ts_query)) | (base_vector.op("@@")(ts_query)),
                       DocumentChunk.document_id.not_in(seen) if seen else True)
                .order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
                .limit(keyword_limit - len(keyword_rows))
            )).all())

    semantic_rows = []
    embedding_status = "disabled"
    if is_embedding_provider_configured() and int(document_count or 0) > 0:
        embedding_status = "available"
        try:
            query_vector = (await embed_texts([search_text[:2000]]))[0].values
            distance = DocumentEmbedding.embedding.op("<=>")(
                literal(query_vector, type_=Vector())
            )
            semantic_query = (
                select(
                       DocumentChunk.document_id,
                       KnowledgeDocument.name.label("document_name"),
                       KnowledgeBase.name.label("knowledge_base_name"),
                       DocumentChunk.chunk_index, DocumentChunk.content, distance.label("distance"))
                .join(DocumentEmbedding,
                      (DocumentEmbedding.organization_id == DocumentChunk.organization_id)
                      & (DocumentEmbedding.document_id == DocumentChunk.document_id)
                      & (DocumentEmbedding.chunk_index == DocumentChunk.chunk_index))
                .join(KnowledgeDocument,
                      (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
                      & (KnowledgeDocument.id == DocumentChunk.document_id))
                .join(KnowledgeBase,
                      (KnowledgeBase.organization_id == KnowledgeDocument.organization_id)
                      & (KnowledgeBase.id == KnowledgeDocument.knowledge_base_id))
                .where(*common_filters,
                       DocumentEmbedding.organization_id == organization_id,
                       DocumentEmbedding.embedding_model == settings.ai_embedding_model,
                       DocumentEmbedding.embedding_version == settings.ai_embedding_version,
                       DocumentEmbedding.dimensions == settings.ai_embedding_dimensions)
            )
            if settings.ai_retrieval_similarity_threshold is not None:
                semantic_query = semantic_query.where(
                    distance <= (1.0 - settings.ai_retrieval_similarity_threshold)
                )
            semantic_rows = list((await db.execute(
                semantic_query.order_by(distance, DocumentChunk.document_id, DocumentChunk.chunk_index)
                .limit(semantic_limit)
            )).all())
        except EmbeddingProviderError as exc:
            embedding_status = exc.code
            logger.warning("knowledge_embedding_query_failed", extra={
                "organization_id": str(organization_id), "ai_agent_id": str(ai_agent_id),
                "error_code": exc.code,
            })

    merged: dict[tuple[UUID, int], dict[str, object]] = {}
    for rank_index, row in enumerate(keyword_rows, start=1):
        key = (row.document_id, row.chunk_index)
        merged[key] = {
            "row": row, "keyword_rank": rank_index, "semantic_rank": None,
            "similarity": None, "basis": row.match_basis,
            "score": reciprocal_rank_fusion(rank_index, None),
        }
    for rank_index, row in enumerate(semantic_rows, start=1):
        key = (row.document_id, row.chunk_index)
        candidate = merged.get(key)
        similarity = 1.0 - float(row.distance)
        if candidate is None:
            candidate = {"row": row, "keyword_rank": None, "semantic_rank": rank_index,
                         "similarity": similarity, "basis": "semantic", "score": 0.0}
            merged[key] = candidate
        else:
            candidate["semantic_rank"] = rank_index
            candidate["similarity"] = similarity
            candidate["basis"] = "hybrid"
        candidate["score"] = reciprocal_rank_fusion(
            int(candidate["keyword_rank"]) if candidate["keyword_rank"] is not None else None,
            rank_index,
        )

    ranked = sorted(merged.values(), key=lambda item: (
        -float(item["score"]), str(item["row"].document_id), int(item["row"].chunk_index)
    ))
    matches: list[KnowledgeMatch] = []
    remaining_tokens = settings.ai_retrieval_token_budget
    seen_excerpts: set[str] = set()
    for candidate in ranked:
        row = candidate["row"]
        excerpt = " ".join(row.content.split())[:800]
        normalized_excerpt = excerpt.casefold()
        if settings.ai_retrieval_dedupe and normalized_excerpt in seen_excerpts:
            continue
        seen_excerpts.add(normalized_excerpt)
        estimated_tokens = max(1, (len(excerpt) + 3) // 4)
        if estimated_tokens > remaining_tokens:
            continue
        remaining_tokens -= estimated_tokens
        matches.append(KnowledgeMatch(
            document_id=row.document_id,
            document_name=row.document_name,
            knowledge_base_name=row.knowledge_base_name,
            chunk_index=row.chunk_index,
            excerpt=excerpt,
            match_basis=str(candidate["basis"]),
            rrf_score=round(float(candidate["score"]), 6),
            semantic_similarity=(round(float(candidate["similarity"]), 6)
                                 if candidate["similarity"] is not None else None),
            keyword_rank=(int(candidate["keyword_rank"])
                          if candidate["keyword_rank"] is not None else None),
            semantic_rank=(int(candidate["semantic_rank"])
                           if candidate["semantic_rank"] is not None else None),
        ))
        if len(matches) >= result_limit:
            break
    method = "hybrid" if any(item.semantic_rank for item in merged.values()) and keyword_rows else (
        "semantic" if semantic_rows else "keyword" if keyword_rows else "none"
    )
    latency_ms = round((time.monotonic() - started) * 1000)
    logger.info("knowledge_retrieval_complete", extra={
        "organization_id": str(organization_id), "ai_agent_id": str(ai_agent_id),
        "retrieval_method": method, "keyword_candidates": len(keyword_rows),
        "semantic_candidates": len(semantic_rows), "matched_chunks": len(matches),
        "latency_ms": latency_ms, "embedding_status": embedding_status,
    })
    return KnowledgeSearchResult(int(base_count or 0), int(document_count or 0),
                                 bool(terms), matches, method, latency_ms, embedding_status)


async def citations_remain_authorized(
    db: AsyncSession,
    *,
    organization_id: UUID,
    ai_agent_id: UUID,
    citations: list[dict[str, str | int]],
) -> bool:
    """Confirm cited documents remain active sources assigned to this bot."""
    document_ids: set[UUID] = set()
    for citation in citations:
        raw_document_id = citation.get("document_id")
        if not isinstance(raw_document_id, str):
            return False
        try:
            document_ids.add(UUID(raw_document_id))
        except ValueError:
            return False
    if not document_ids:
        return not citations

    agent = await db.scalar(
        select(AIAgent)
        .where(
            AIAgent.organization_id == organization_id,
            AIAgent.id == ai_agent_id,
            AIAgent.status == "active",
        )
        .with_for_update()
    )
    if agent is None:
        return False

    source_rows = (
        await db.execute(
            select(KnowledgeDocument.id, KnowledgeBase.id)
            .select_from(AIAgent)
            .join(
                AIAgentKnowledgeBase,
                (AIAgentKnowledgeBase.organization_id == AIAgent.organization_id)
                & (AIAgentKnowledgeBase.ai_agent_id == AIAgent.id),
            )
            .join(
                KnowledgeBase,
                (KnowledgeBase.organization_id == AIAgentKnowledgeBase.organization_id)
                & (KnowledgeBase.id == AIAgentKnowledgeBase.knowledge_base_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
                & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id),
            )
            .where(
                AIAgent.organization_id == organization_id,
                AIAgent.id == ai_agent_id,
                AIAgent.status == "active",
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.id.in_(document_ids),
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeBase.status == "active",
            )
        )
    ).all()
    if {document_id for document_id, _ in source_rows} != document_ids:
        return False
    base_ids = {base_id for _, base_id in source_rows}

    # Follow document-move lock order (document IDs, then base IDs). Holding
    # these rows through the caller's commit serializes authorization with
    # deletion, reprocessing, moves, and archival.
    locked_documents = set(
        await db.scalars(
            select(KnowledgeDocument.id)
            .where(
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.id.in_(document_ids),
            )
            .order_by(KnowledgeDocument.id)
            .with_for_update()
        )
    )
    if locked_documents != document_ids:
        return False
    locked_bases = set(
        await db.scalars(
            select(KnowledgeBase.id)
            .where(
                KnowledgeBase.organization_id == organization_id,
                KnowledgeBase.id.in_(base_ids),
            )
            .order_by(KnowledgeBase.id)
            .with_for_update()
        )
    )
    if locked_bases != base_ids:
        return False

    authorized_ids = set(
        await db.scalars(
            select(KnowledgeDocument.id)
            .select_from(AIAgent)
            .join(
                AIAgentKnowledgeBase,
                (AIAgentKnowledgeBase.organization_id == AIAgent.organization_id)
                & (AIAgentKnowledgeBase.ai_agent_id == AIAgent.id),
            )
            .join(
                KnowledgeBase,
                (KnowledgeBase.organization_id == AIAgentKnowledgeBase.organization_id)
                & (KnowledgeBase.id == AIAgentKnowledgeBase.knowledge_base_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
                & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id),
            )
            .where(
                AIAgent.organization_id == organization_id,
                AIAgent.id == ai_agent_id,
                AIAgent.status == "active",
                KnowledgeDocument.organization_id == organization_id,
                KnowledgeDocument.id.in_(document_ids),
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.deleted_at.is_(None),
                KnowledgeBase.status == "active",
            )
        )
    )
    return authorized_ids == document_ids
