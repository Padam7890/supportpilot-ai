from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class WidgetConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_origins: list[str] = Field(min_length=1, max_length=25)
    collect_contact: bool = True
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"


class WidgetConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_origins: list[str] = Field(min_length=1, max_length=25)
    enabled: bool = True
    collect_contact: bool = True
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"


class WidgetConfigOut(BaseModel):
    public_id: str
    allowed_origins: list[str]
    enabled: bool
    collect_contact: bool
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"
    created_at: datetime


class PublicWidgetConfigOut(BaseModel):
    store_name: str
    collect_contact: bool
    welcome_message: str = "Hi! How can we help?"


class WidgetFirstMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    visitor_name: str | None = Field(default=None, max_length=120)
    visitor_email: EmailStr | None = None
    contact_consent: bool = False
    website: str | None = Field(default=None, max_length=200)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be blank")
        return cleaned

    @field_validator("visitor_name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        cleaned = value.strip() if value else None
        return cleaned or None

    @model_validator(mode="after")
    def consent_for_contact_details(self):
        if (self.visitor_name or self.visitor_email) and not self.contact_consent:
            raise ValueError("Consent is required when providing contact details")
        return self


class WidgetMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    website: str | None = Field(default=None, max_length=200)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be blank")
        return cleaned


class WidgetStartOut(BaseModel):
    ticket_id: UUID
    conversation_id: UUID
    visitor_token: str
    visitor_token_expires_at: datetime
    confirmation: str


class WidgetMessageOut(BaseModel):
    id: UUID
    sender_type: str
    content: str
    created_at: datetime


class WidgetConversationOut(BaseModel):
    conversation_id: UUID
    messages: list[WidgetMessageOut]


class WidgetOrderVerificationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_number: str = Field(min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$")
    email: EmailStr


class WidgetOrderVerificationCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class WidgetOrderVerificationOut(BaseModel):
    message: str
    verified: bool = False
    order_number: str | None = None
    financial_status: str | None = None
    fulfillment_status: str | None = None
    tracking: list[dict[str, str | None]] = Field(default_factory=list)

