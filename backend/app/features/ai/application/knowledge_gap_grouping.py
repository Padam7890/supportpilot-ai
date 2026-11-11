"""Tenant-scoped semantic grouping of knowledge gap questions.

Groups are computed from configured embeddings, never hardcoded keywords.
This service is read-only and does not publish knowledge.
"""
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai.infrastructure.embedding_gateway import embed_texts
from app.core.config import settings
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_gap_embedding import KnowledgeGapEmbedding


@dataclass(frozen=True)
class GapGroup:
    representative: str
    count: int
    gap_ids: tuple[UUID, ...]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must have the same nonzero dimensions")
    denominator = sqrt(sum(v * v for v in left)) * sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0


def group_vectors(
    questions: list[tuple[UUID, str]],
    vectors: list[list[float]],
    *,
    threshold: float = 0.86,
) -> list[GapGroup]:
    if len(questions) != len(vectors) or not 0.0 < threshold <= 1.0:
        raise ValueError("Invalid grouping inputs")
    representatives: list[int] = []
    members: list[list[int]] = []
    for index, vector in enumerate(vectors):
        best = -1
        best_score = threshold
        for group_index, representative in enumerate(representatives):
            score = cosine_similarity(vector, vectors[representative])
            if score >= best_score:
                best, best_score = group_index, score
        if best < 0:
            representatives.append(index)
            members.append([index])
        else:
            members[best].append(index)
    return [
        GapGroup(questions[representative][1], len(indices), tuple(questions[i][0] for i in indices))
        for representative, indices in zip(representatives, members, strict=True)
    ]


async def list_semantic_groups(
    db: AsyncSession,
    *,
    organization_id: UUID,
    limit: int = 100,
) -> list[GapGroup]:
    """Bounded review-time grouping; tenant-scoped before embedding."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    rows = (await db.scalars(
        select(KnowledgeGap)
        .where(KnowledgeGap.organization_id == organization_id, KnowledgeGap.status == "open")
        .order_by(KnowledgeGap.created_at.desc(), KnowledgeGap.id.desc())
        .limit(limit)
    )).all()
    if not rows:
        return []
    model = settings.ai_embedding_model
    version = settings.ai_embedding_version
    if not model:
        raise ValueError("Embedding model is not configured")
    cached = (await db.scalars(
        select(KnowledgeGapEmbedding).where(
            KnowledgeGapEmbedding.organization_id == organization_id,
            KnowledgeGapEmbedding.gap_id.in_([row.id for row in rows]),
            KnowledgeGapEmbedding.model == model,
            KnowledgeGapEmbedding.version == version,
        )
    )).all()
    by_id = {item.gap_id: item for item in cached}
    vectors_by_id: dict[UUID, list[float]] = {}
    missing = []
    for row in rows:
        digest = sha256(row.question.encode("utf-8")).hexdigest()
        item = by_id.get(row.id)
        if item and item.question_hash == digest and len(item.values) == item.dimensions:
            vectors_by_id[row.id] = item.values
        else:
            missing.append((row, digest))
    batch_size = max(1, settings.ai_embedding_batch_size)
    for offset in range(0, len(missing), batch_size):
        batch = missing[offset:offset + batch_size]
        embedded = await embed_texts([row.question for row, _ in batch], model=model)
        if len(embedded) != len(batch):
            raise ValueError("Embedding provider returned the wrong vector count")
        for (row, digest), vector in zip(batch, embedded, strict=True):
            vectors_by_id[row.id] = vector.values
            stmt = insert(KnowledgeGapEmbedding).values(
                organization_id=organization_id, gap_id=row.id, model=model,
                version=version, question_hash=digest,
                dimensions=len(vector.values), values=vector.values,
            ).on_conflict_do_update(
                index_elements=["organization_id", "gap_id", "model", "version"],
                set_={"question_hash": digest, "dimensions": len(vector.values), "values": vector.values},
            )
            await db.execute(stmt)
    # get_db commits the cache writes at request completion.
    return group_vectors(
        [(row.id, row.question) for row in rows],
        [vectors_by_id[row.id] for row in rows],
    )
