"""Tenant- and bot-scoped full-text search shared by AI runs and diagnostics."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai.application.retrieval import build_retrieval_terms
from app.models import (
    AIAgent,
    AIAgentKnowledgeBase,
    DocumentChunk,
    KnowledgeBase,
    KnowledgeDocument,
)


@dataclass(frozen=True)
class KnowledgeMatch:
    document_id: UUID
    document_name: str
    knowledge_base_name: str
    chunk_index: int
    excerpt: str
    match_basis: str


@dataclass(frozen=True)
class KnowledgeSearchResult:
    active_assigned_base_count: int
    ready_document_count: int
    terms_available: bool
    matches: list[KnowledgeMatch]


async def search_agent_knowledge(
    db: AsyncSession,
    *,
    organization_id: UUID,
    ai_agent_id: UUID,
    search_text: str,
    limit: int = 6,
) -> KnowledgeSearchResult:
    """Search only ready documents from the active bases assigned to this bot."""
    assigned_bases = (
        select(AIAgentKnowledgeBase.knowledge_base_id)
        .join(
            AIAgent,
            (AIAgent.organization_id == AIAgentKnowledgeBase.organization_id)
            & (AIAgent.id == AIAgentKnowledgeBase.ai_agent_id),
        )
        .join(
            KnowledgeBase,
            (KnowledgeBase.organization_id == AIAgentKnowledgeBase.organization_id)
            & (KnowledgeBase.id == AIAgentKnowledgeBase.knowledge_base_id),
        )
        .where(
            AIAgentKnowledgeBase.organization_id == organization_id,
            AIAgentKnowledgeBase.ai_agent_id == ai_agent_id,
            AIAgent.status == "active",
            KnowledgeBase.status == "active",
        )
    )
    base_count, document_count = (
        await db.execute(
            select(
                func.count(func.distinct(KnowledgeBase.id)),
                func.count(func.distinct(KnowledgeDocument.id)),
            )
            .join(
                AIAgentKnowledgeBase,
                (AIAgentKnowledgeBase.organization_id == KnowledgeBase.organization_id)
                & (AIAgentKnowledgeBase.knowledge_base_id == KnowledgeBase.id)
                & (AIAgentKnowledgeBase.ai_agent_id == ai_agent_id),
            )
            .join(
                AIAgent,
                (AIAgent.organization_id == AIAgentKnowledgeBase.organization_id)
                & (AIAgent.id == AIAgentKnowledgeBase.ai_agent_id)
                & (AIAgent.status == "active"),
            )
            .outerjoin(
                KnowledgeDocument,
                (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
                & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                & (KnowledgeDocument.status == "ready")
                & KnowledgeDocument.deleted_at.is_(None),
            )
            .where(
                KnowledgeBase.organization_id == organization_id,
                KnowledgeBase.status == "active",
                AIAgentKnowledgeBase.organization_id == organization_id,
            )
        )
    ).one()
    terms = build_retrieval_terms(search_text)
    if not terms:
        return KnowledgeSearchResult(int(base_count or 0), int(document_count or 0), False, [])

    simple_config = literal_column("'simple'::regconfig")
    ts_query = func.to_tsquery(simple_config, " | ".join(terms))
    # Match titles and the assigned base label as well as chunk text. This is
    # especially useful when headings carry the intent (for example, a source
    # named "Delivery and tracking" whose body uses different wording). The
    # weighted vector remains entirely inside the same tenant/bot scoped query.
    content_vector = func.to_tsvector(simple_config, DocumentChunk.content)
    document_name_vector = func.to_tsvector(simple_config, KnowledgeDocument.name)
    base_name_vector = func.to_tsvector(simple_config, KnowledgeBase.name)
    search_vector = (
        func.setweight(
            document_name_vector,
            literal_column("'A'::\"char\""),
        )
        .op("||")(
            func.setweight(
                base_name_vector,
                literal_column("'B'::\"char\""),
            )
        )
        .op("||")(
            func.setweight(
                content_vector,
                literal_column("'C'::\"char\""),
            )
        )
    )
    rank = func.ts_rank_cd(search_vector, ts_query)
    max_results = max(1, min(limit, 10))
    common_filters = (
        DocumentChunk.organization_id == organization_id,
        KnowledgeDocument.status == "ready",
        KnowledgeDocument.deleted_at.is_(None),
        KnowledgeDocument.knowledge_base_id.in_(assigned_bases),
        KnowledgeBase.status == "active",
    )
    source_query = (
        select(
            DocumentChunk.document_id,
            KnowledgeDocument.name,
            KnowledgeBase.name,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
        )
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
            & (KnowledgeDocument.id == DocumentChunk.document_id),
        )
        .join(
            KnowledgeBase,
            (KnowledgeBase.organization_id == KnowledgeDocument.organization_id)
            & (KnowledgeBase.id == KnowledgeDocument.knowledge_base_id),
        )
        .where(*common_filters)
    )
    rows = (
        await db.execute(
            source_query
            .add_columns(literal("chunk_content").label("match_basis"))
            .where(content_vector.op("@@")(ts_query))
            .order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(max_results)
        )
    ).all()
    if len(rows) < max_results:
        seen_document_ids = {row.document_id for row in rows}
        metadata_matches = (
            await db.execute(
                source_query
                .add_columns(literal("source_title").label("match_basis"))
                .where(
                    (document_name_vector.op("@@")(ts_query))
                    | (base_name_vector.op("@@")(ts_query)),
                    DocumentChunk.document_id.not_in(seen_document_ids)
                    if seen_document_ids
                    else True,
                )
                .order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
                .limit(max_results - len(rows))
            )
        ).all()
        rows.extend(metadata_matches)
    matches = [
        KnowledgeMatch(
            document_id=document_id,
            document_name=document_name,
            knowledge_base_name=base_name,
            chunk_index=chunk_index,
            excerpt=" ".join(content.split())[:800],
            match_basis=match_basis,
        )
        for document_id, document_name, base_name, chunk_index, content, match_basis in rows
    ]
    return KnowledgeSearchResult(int(base_count or 0), int(document_count or 0), True, matches)


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
