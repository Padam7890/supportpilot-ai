"""Read model for the customer-question review dashboard."""
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_gap_group import KnowledgeGapGroup, KnowledgeGapGroupMember

QuestionView = Literal["all", "grouped", "ungrouped"]


class DashboardQuestion(BaseModel):
    id: UUID
    question: str
    created_at: datetime


class DashboardGroup(BaseModel):
    id: UUID | None
    representative: str
    questions: list[DashboardQuestion]


class DashboardCounts(BaseModel):
    total: int
    open: int
    resolved: int
    grouped: int
    groups: int


class KnowledgeGapDashboard(BaseModel):
    items: list[DashboardGroup]
    counts: DashboardCounts
    has_more: bool


async def load_knowledge_gap_dashboard(
    db: AsyncSession,
    organization_id: UUID,
    *,
    days: int | None,
    view: QuestionView,
    search: str,
    limit: int,
    offset: int,
) -> KnowledgeGapDashboard:
    member = KnowledgeGapGroupMember
    group = KnowledgeGapGroup
    scope = [KnowledgeGap.organization_id == organization_id]
    if days is not None:
        scope.append(KnowledgeGap.created_at >= datetime.now(UTC) - timedelta(days=days))

    member_join = (member.organization_id == KnowledgeGap.organization_id) & (member.gap_id == KnowledgeGap.id)
    is_open = KnowledgeGap.status == "open"
    total, open_count, resolved, grouped, groups = (await db.execute(
        select(
            func.count(KnowledgeGap.id),
            func.count(KnowledgeGap.id).filter(is_open),
            func.count(KnowledgeGap.id).filter(KnowledgeGap.status == "resolved"),
            func.count(member.group_id).filter(is_open),
            func.count(distinct(member.group_id)).filter(is_open),
        ).select_from(KnowledgeGap).outerjoin(member, member_join).where(*scope)
    )).one()

    query = (
        select(KnowledgeGap.id, KnowledgeGap.question, KnowledgeGap.created_at, group.id, group.representative)
        .select_from(KnowledgeGap).outerjoin(member, member_join)
        .outerjoin(group, (group.organization_id == member.organization_id) & (group.id == member.group_id))
        .where(*scope, is_open)
    )
    if view == "grouped":
        query = query.where(member.group_id.is_not(None))
    elif view == "ungrouped":
        query = query.where(member.group_id.is_(None))
    if search:
        query = query.where(KnowledgeGap.question.icontains(search, autoescape=True))

    rows = (await db.execute(
        query.order_by(KnowledgeGap.created_at.desc(), KnowledgeGap.id.desc()).offset(offset).limit(limit + 1)
    )).tuples().all()
    return KnowledgeGapDashboard(
        items=_group_questions(rows[:limit]),
        counts=DashboardCounts(total=total, open=open_count, resolved=resolved, grouped=grouped, groups=groups),
        has_more=len(rows) > limit,
    )


def _group_questions(
    rows: Sequence[tuple[UUID, str, datetime, UUID | None, str | None]],
) -> list[DashboardGroup]:
    groups: dict[UUID, DashboardGroup] = {}
    for gap_id, question, created_at, group_id, representative in rows:
        key = group_id or gap_id
        if key not in groups:
            groups[key] = DashboardGroup(id=group_id, representative=representative or question, questions=[])
        groups[key].questions.append(DashboardQuestion(id=gap_id, question=question, created_at=created_at))
    return list(groups.values())
