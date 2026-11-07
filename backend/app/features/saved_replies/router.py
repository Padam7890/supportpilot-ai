from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import SavedReply, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.features.saved_replies.schemas import SavedReplyCreate, SavedReplyOut, SavedReplyUpdate

router = APIRouter(prefix="/saved-replies", tags=["saved-replies"], responses=COMMON_ERROR_RESPONSES)


@router.get("", response_model=list[SavedReplyOut])
async def list_saved_replies(
    include_archived: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SavedReplyOut]:
    if include_archived and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only Owners and Admins can view archived replies")
    query = select(SavedReply).where(SavedReply.organization_id == user.organization_id)
    if not include_archived:
        query = query.where(SavedReply.is_active.is_(True))
    rows = await db.scalars(query.order_by(SavedReply.title, SavedReply.id).limit(200))
    return [SavedReplyOut.model_validate(row) for row in rows]


@router.post("", response_model=SavedReplyOut, status_code=201)
async def create_saved_reply(
    data: SavedReplyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> SavedReplyOut:
    if await _shortcut_exists(db, user.organization_id, data.shortcut):
        raise HTTPException(status_code=409, detail="That shortcut is already in use")
    item = SavedReply(
        organization_id=user.organization_id,
        title=data.title,
        shortcut=data.shortcut,
        body=data.body,
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="That shortcut is already in use") from exc
    return SavedReplyOut.model_validate(item)


@router.patch("/{saved_reply_id}", response_model=SavedReplyOut)
async def update_saved_reply(
    saved_reply_id: UUID,
    data: SavedReplyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> SavedReplyOut:
    item = await _get_saved_reply(db, user.organization_id, saved_reply_id)
    changes = data.model_dump(exclude_unset=True)
    new_shortcut = changes.get("shortcut")
    if new_shortcut and new_shortcut != item.shortcut and await _shortcut_exists(
        db, user.organization_id, new_shortcut
    ):
        raise HTTPException(status_code=409, detail="That shortcut is already in use")
    for field, value in changes.items():
        setattr(item, field, value)
    item.updated_by_user_id = user.id
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="That shortcut is already in use") from exc
    return SavedReplyOut.model_validate(item)


@router.delete("/{saved_reply_id}", response_model=SavedReplyOut)
async def archive_saved_reply(
    saved_reply_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> SavedReplyOut:
    item = await _get_saved_reply(db, user.organization_id, saved_reply_id)
    item.is_active = False
    item.updated_by_user_id = user.id
    await db.flush()
    return SavedReplyOut.model_validate(item)


async def _get_saved_reply(db: AsyncSession, organization_id: UUID, item_id: UUID) -> SavedReply:
    item = await db.scalar(
        select(SavedReply).where(
            SavedReply.organization_id == organization_id,
            SavedReply.id == item_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Saved reply not found")
    return item


async def _shortcut_exists(db: AsyncSession, organization_id: UUID, shortcut: str) -> bool:
    return bool(
        await db.scalar(
            select(SavedReply.id).where(
                SavedReply.organization_id == organization_id,
                SavedReply.shortcut == shortcut,
            )
        )
    )
