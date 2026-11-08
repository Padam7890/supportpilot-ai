from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.recommendations import ProductComparisonResult, RecommendationResult


class WidgetConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_origins: list[str] = Field(min_length=1, max_length=25)
    collect_contact: bool = True
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"
    assistant_name: str = Field(default="SupportPilot AI", min_length=1, max_length=60)
    welcome_message: str = Field(default="Hi! How can we help?", min_length=1, max_length=240)
    ai_agent_id: UUID | None = None
    ai_agent_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("assistant_name", "welcome_message")
    @classmethod
    def normalize_widget_copy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Widget text cannot be blank")
        return cleaned


class WidgetConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_origins: list[str] = Field(min_length=1, max_length=25)
    enabled: bool = True
    collect_contact: bool = True
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"
    assistant_name: str | None = Field(default=None, min_length=1, max_length=60)
    welcome_message: str | None = Field(default=None, min_length=1, max_length=240)
    ai_agent_id: UUID | None = None
    ai_agent_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("assistant_name", "welcome_message")
    @classmethod
    def normalize_widget_copy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Widget text cannot be blank")
        return cleaned


class WidgetConfigOut(BaseModel):
    public_id: str
    ai_agent_id: UUID
    ai_agent_ids: list[UUID] = Field(default_factory=list)
    allowed_origins: list[str]
    enabled: bool
    collect_contact: bool
    ai_enabled: bool = False
    ai_reply_mode: Literal["draft_only", "auto_reply"] = "draft_only"
    assistant_name: str = "SupportPilot AI"
    welcome_message: str = "Hi! How can we help?"
    last_widget_load_at: datetime | None = None
    last_customer_message_at: datetime | None = None
    created_at: datetime


class WidgetRoutingPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    ai_agent_ids: list[UUID] = Field(min_length=1, max_length=10)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a sample customer message")
        return cleaned


class WidgetRoutingPreviewOut(BaseModel):
    ai_agent_id: UUID
    ai_agent_name: str
    configured_bot_count: int
    routing_reason: Literal[
        "best_source_match",
        "primary_fallback",
        "conversation_continuity",
        "conversation_override",
    ]
    matched_bot_count: int = Field(ge=0, le=10)
    routing_rule: Literal["best_source_match_then_primary_fallback"] = "best_source_match_then_primary_fallback"


class PublicWidgetConfigOut(BaseModel):
    store_name: str
    collect_contact: bool
    ai_enabled: bool = False
    assistant_name: str = "SupportPilot AI"
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


class WidgetRecommendationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_id: UUID
    variant_id: UUID


class WidgetMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=4000)
    website: str | None = Field(default=None, max_length=200)
    recommendation_selections: list["WidgetRecommendationSelection"] | None = Field(default=None, max_length=4)

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
    recommendation: RecommendationResult | ProductComparisonResult | None = None


class WidgetConversationOut(BaseModel):
    conversation_id: UUID
    messages: list[WidgetMessageOut]
    order_verified: bool = False
    ai_mode: str = "human"


class WidgetOrderVerificationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_number: str = Field(min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$")
    email: EmailStr
    consent: bool


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


class WidgetCancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 5:
            raise ValueError("Please provide a short reason for the cancellation request")
        return cleaned

