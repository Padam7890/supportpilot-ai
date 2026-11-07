from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    uploaded_by_user_id: UUID
    uploaded_by_name: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
