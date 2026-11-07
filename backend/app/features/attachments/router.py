from pathlib import PurePath
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.attachments.policy import (
    ALLOWED_ATTACHMENT_TYPES,
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_CONVERSATION,
    MAX_CONVERSATION_ATTACHMENT_BYTES,
)
from app.features.attachments.schemas import ConversationAttachmentOut
from app.models import Conversation, ConversationAttachment, TicketActivity, User
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["attachments"], responses=COMMON_ERROR_RESPONSES)


async def _owned_conversation(
    db: AsyncSession,
    organization_id: UUID,
    conversation_id: UUID,
    *,
    lock: bool = False,
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.organization_id == organization_id,
        Conversation.id == conversation_id,
    )
    if lock:
        statement = statement.with_for_update()
    conversation = await db.scalar(statement)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def _attachment_out(db: AsyncSession, item: ConversationAttachment) -> ConversationAttachmentOut:
    name = await db.scalar(select(User.full_name).where(
        User.organization_id == item.organization_id,
        User.id == item.uploaded_by_user_id,
    ))
    return ConversationAttachmentOut(
        id=item.id,
        conversation_id=item.conversation_id,
        uploaded_by_user_id=item.uploaded_by_user_id,
        uploaded_by_name=name or "Teammate",
        original_filename=item.original_filename,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        created_at=item.created_at,
    )


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=ConversationAttachmentOut,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in sorted({item[0] for item in ALLOWED_ATTACHMENT_TYPES.values()})
            },
        }
    },
)
async def upload_conversation_attachment(
    conversation_id: UUID,
    request: Request,
    name: str = Query(min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ConversationAttachmentOut:
    conversation = await _owned_conversation(db, user.organization_id, conversation_id, lock=True)
    filename = PurePath(name.replace("\\", "/")).name.strip()
    suffix = PurePath(filename).suffix.casefold()
    file_rule = ALLOWED_ATTACHMENT_TYPES.get(suffix)
    mime = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if not filename or file_rule is None or mime != file_rule[0]:
        raise HTTPException(status_code=415, detail="Attach a PNG, JPEG, WebP, PDF, TXT, or Markdown file")

    attachment_count = await db.scalar(
        select(func.count(ConversationAttachment.id)).where(
            ConversationAttachment.organization_id == user.organization_id,
            ConversationAttachment.conversation_id == conversation.id,
        )
    )
    if (attachment_count or 0) >= MAX_ATTACHMENTS_PER_CONVERSATION:
        raise HTTPException(
            status_code=409,
            detail=f"This conversation already has the maximum of {MAX_ATTACHMENTS_PER_CONVERSATION} team files",
        )

    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Attachments are limited to 10 MB")
        content.extend(chunk)
    payload = bytes(content)
    if not payload:
        raise HTTPException(status_code=400, detail="Attachment is empty")
    if not file_rule[1](payload):
        raise HTTPException(status_code=415, detail="File content does not match its declared type")

    total_size = await db.scalar(
        select(func.coalesce(func.sum(ConversationAttachment.size_bytes), 0)).where(
            ConversationAttachment.organization_id == user.organization_id,
            ConversationAttachment.conversation_id == conversation.id,
        )
    )
    if (total_size or 0) + len(payload) > MAX_CONVERSATION_ATTACHMENT_BYTES:
        total_limit_mb = MAX_CONVERSATION_ATTACHMENT_BYTES // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Team files for this conversation are limited to {total_limit_mb} MB total")

    item = ConversationAttachment(
        organization_id=user.organization_id,
        conversation_id=conversation.id,
        uploaded_by_user_id=user.id,
        original_filename=filename,
        content_type=mime,
        size_bytes=len(payload),
        content=payload,
    )
    db.add(item)
    await db.flush()
    db.add(TicketActivity(
        organization_id=user.organization_id,
        ticket_id=conversation.ticket_id,
        actor_user_id=user.id,
        activity_type="updated",
        details={"attachment_added": {"attachment_id": str(item.id), "size_bytes": len(payload), "content_type": mime}},
    ))
    await db.flush()
    return await _attachment_out(db, item)


@router.get("/conversations/{conversation_id}/attachments", response_model=list[ConversationAttachmentOut])
async def list_conversation_attachments(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationAttachmentOut]:
    await _owned_conversation(db, user.organization_id, conversation_id)
    rows = await db.execute(
        select(ConversationAttachment, User.full_name)
        .join(
            User,
            (User.organization_id == ConversationAttachment.organization_id)
            & (User.id == ConversationAttachment.uploaded_by_user_id),
        )
        .where(
            ConversationAttachment.organization_id == user.organization_id,
            ConversationAttachment.conversation_id == conversation_id,
        )
        .order_by(ConversationAttachment.created_at, ConversationAttachment.id)
        .limit(100)
    )
    return [
        ConversationAttachmentOut(
            id=item.id,
            conversation_id=item.conversation_id,
            uploaded_by_user_id=item.uploaded_by_user_id,
            uploaded_by_name=uploader_name or "Teammate",
            original_filename=item.original_filename,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
            created_at=item.created_at,
        )
        for item, uploader_name in rows
    ]


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    item = await db.scalar(
        select(ConversationAttachment)
        .options(undefer(ConversationAttachment.content))
        .where(
            ConversationAttachment.organization_id == user.organization_id,
            ConversationAttachment.id == attachment_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(
        content=item.content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(item.original_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> None:
    item = await db.scalar(select(ConversationAttachment).where(
        ConversationAttachment.organization_id == user.organization_id,
        ConversationAttachment.id == attachment_id,
    ).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if item.uploaded_by_user_id != user.id and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only the uploader or a workspace Owner/Admin can remove this attachment")
    conversation = await _owned_conversation(db, user.organization_id, item.conversation_id)
    db.add(TicketActivity(
        organization_id=user.organization_id,
        ticket_id=conversation.ticket_id,
        actor_user_id=user.id,
        activity_type="updated",
        details={"attachment_removed": {"attachment_id": str(item.id)}},
    ))
    await db.execute(delete(ConversationAttachment).where(
        ConversationAttachment.organization_id == user.organization_id,
        ConversationAttachment.id == item.id,
    ))
