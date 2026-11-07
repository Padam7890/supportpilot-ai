from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import KnowledgeBase, KnowledgeBaseAudit, KnowledgeDocument, User
from app.services.knowledge_base_audit import record_knowledge_base_audit
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.knowledge_bases import (
    KnowledgeBaseCreate,
    KnowledgeBaseAuditOut,
    KnowledgeBaseAuditPage,
    KnowledgeBaseListItem,
    KnowledgeBaseOut,
    KnowledgeBasePage,
    KnowledgeBaseUpdate,
)

router = APIRouter(prefix="/knowledge/bases", tags=["knowledge bases"], responses=COMMON_ERROR_RESPONSES)


@router.get("", response_model=KnowledgeBasePage)
async def list_knowledge_bases(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBasePage:
    predicate = KnowledgeBase.organization_id == user.organization_id
    total = await db.scalar(select(func.count()).select_from(KnowledgeBase).where(predicate)) or 0
    rows = await db.execute(
        select(
            KnowledgeBase,
            func.count(KnowledgeDocument.id).label("document_count"),
            func.count(case((KnowledgeDocument.status == "ready", 1))).label("ready_document_count"),
            func.count(case((KnowledgeDocument.status.in_(("queued", "processing")), 1))).label("processing_document_count"),
            func.count(case((KnowledgeDocument.status == "failed", 1))).label("failed_document_count"),
        )
        .outerjoin(
            KnowledgeDocument,
            (KnowledgeDocument.organization_id == KnowledgeBase.organization_id)
            & (KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            & KnowledgeDocument.deleted_at.is_(None),
        )
        .where(predicate)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.is_default.desc(), KnowledgeBase.created_at, KnowledgeBase.id)
        .limit(limit)
        .offset(offset)
    )
    items = [
        KnowledgeBaseListItem(
            **KnowledgeBaseOut.model_validate(base).model_dump(),
            document_count=document_count,
            ready_document_count=ready_document_count,
            processing_document_count=processing_document_count,
            failed_document_count=failed_document_count,
        )
        for base, document_count, ready_document_count, processing_document_count, failed_document_count in rows
    ]
    return KnowledgeBasePage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseOut:
    base = KnowledgeBase(organization_id=user.organization_id, name=data.name.strip(), description=data.description)
    db.add(base)
    await db.flush()
    record_knowledge_base_audit(
        db,
        organization_id=user.organization_id,
        knowledge_base_id=base.id,
        actor_user_id=user.id,
        event_type="created",
        details={"name": base.name},
    )
    return KnowledgeBaseOut.model_validate(base)


@router.get("/{base_id}", response_model=KnowledgeBaseOut)
async def get_knowledge_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeBaseOut:
    base = await _get_base(db, user.organization_id, base_id)
    return KnowledgeBaseOut.model_validate(base)


@router.get("/{base_id}/audit", response_model=KnowledgeBaseAuditPage)
async def list_knowledge_base_audit(
    base_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseAuditPage:
    await _get_base(db, user.organization_id, base_id)
    predicate = (
        KnowledgeBaseAudit.organization_id == user.organization_id,
        KnowledgeBaseAudit.knowledge_base_id == base_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(KnowledgeBaseAudit).where(*predicate)
    ) or 0
    rows = await db.execute(
        select(KnowledgeBaseAudit, User.full_name)
        .join(
            User,
            (User.organization_id == KnowledgeBaseAudit.organization_id)
            & (User.id == KnowledgeBaseAudit.actor_user_id),
        )
        .where(*predicate)
        .order_by(KnowledgeBaseAudit.created_at.desc(), KnowledgeBaseAudit.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return KnowledgeBaseAuditPage(
        items=[
            KnowledgeBaseAuditOut(
                id=audit.id,
                knowledge_base_id=audit.knowledge_base_id,
                actor_user_id=audit.actor_user_id,
                actor_name=actor_name,
                event_type=audit.event_type,
                details=audit.details,
                created_at=audit.created_at,
            )
            for audit, actor_name in rows.all()
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{base_id}", response_model=KnowledgeBaseOut)
async def update_knowledge_base(
    base_id: UUID,
    data: KnowledgeBaseUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseOut:
    base = await _get_base(db, user.organization_id, base_id, lock=True)
    if base.status != "active":
        raise HTTPException(status_code=409, detail="Archived knowledge bases cannot be edited")
    new_name = data.name.strip()
    changed_fields = []
    if base.name != new_name:
        changed_fields.append("name")
    if base.description != data.description:
        changed_fields.append("description")
    base.name = new_name
    base.description = data.description
    if changed_fields:
        record_knowledge_base_audit(
            db,
            organization_id=user.organization_id,
            knowledge_base_id=base.id,
            actor_user_id=user.id,
            event_type="updated",
            details={"changed_fields": changed_fields, "name": new_name},
        )
    await db.flush()
    return KnowledgeBaseOut.model_validate(base)


@router.post("/{base_id}/archive", response_model=KnowledgeBaseOut)
async def archive_knowledge_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseOut:
    base = await _get_base(db, user.organization_id, base_id, lock=True)
    if base.is_default:
        raise HTTPException(status_code=409, detail="The default knowledge base cannot be archived")
    if base.status != "archived":
        base.status = "archived"
        record_knowledge_base_audit(
            db,
            organization_id=user.organization_id,
            knowledge_base_id=base.id,
            actor_user_id=user.id,
            event_type="archived",
            details={"name": base.name},
        )
    await db.flush()
    return KnowledgeBaseOut.model_validate(base)


@router.post("/{base_id}/restore", response_model=KnowledgeBaseOut)
async def restore_knowledge_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseOut:
    """Reactivate an archived tenant base without changing its document history."""
    base = await _get_base(db, user.organization_id, base_id, lock=True)
    if base.status == "archived":
        base.status = "active"
        record_knowledge_base_audit(
            db,
            organization_id=user.organization_id,
            knowledge_base_id=base.id,
            actor_user_id=user.id,
            event_type="restored",
            details={"name": base.name},
        )
        await db.flush()
    return KnowledgeBaseOut.model_validate(base)


@router.post("/{base_id}/make-default", response_model=KnowledgeBaseOut)
async def make_default_knowledge_base(
    base_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeBaseOut:
    """Set the tenant's active default base for requests without an explicit selection."""
    # Lock all bases in a deterministic order so concurrent default changes in this
    # organization serialize before updating the partial unique default index.
    bases = list(
        await db.scalars(
            select(KnowledgeBase)
            .where(KnowledgeBase.organization_id == user.organization_id)
            .order_by(KnowledgeBase.id)
            .with_for_update()
        )
    )
    target = next((base for base in bases if base.id == base_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if target.status != "active":
        raise HTTPException(status_code=409, detail="An archived knowledge base cannot be the default")
    if target.is_default:
        return KnowledgeBaseOut.model_validate(target)

    previous_default = next((base for base in bases if base.is_default), None)
    for base in bases:
        if base.is_default:
            base.is_default = False
    await db.flush()
    target.is_default = True
    await db.flush()
    if previous_default is not None:
        record_knowledge_base_audit(
            db,
            organization_id=user.organization_id,
            knowledge_base_id=previous_default.id,
            actor_user_id=user.id,
            event_type="default_changed",
            details={"is_default": False, "new_default_id": str(target.id)},
        )
    record_knowledge_base_audit(
        db,
        organization_id=user.organization_id,
        knowledge_base_id=target.id,
        actor_user_id=user.id,
        event_type="default_changed",
        details={"is_default": True, "previous_default_id": str(previous_default.id) if previous_default else None},
    )
    return KnowledgeBaseOut.model_validate(target)


async def _get_base(db: AsyncSession, organization_id: UUID, base_id: UUID, *, lock: bool = False) -> KnowledgeBase:
    statement = select(KnowledgeBase).where(
        KnowledgeBase.id == base_id,
        KnowledgeBase.organization_id == organization_id,
    )
    if lock:
        statement = statement.with_for_update()
    base = await db.scalar(statement)
    if base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return base
