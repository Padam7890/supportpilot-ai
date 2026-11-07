import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SavedReplyCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    shortcut: str = Field(min_length=2, max_length=40)
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("title", "body")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("shortcut")
    @classmethod
    def normalize_shortcut(cls, value: str) -> str:
        normalized = value.strip().casefold().lstrip("/")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,39}", normalized):
            raise ValueError("Use 2–40 letters, numbers, hyphens, or underscores")
        return normalized


class SavedReplyUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    shortcut: str | None = Field(default=None, min_length=2, max_length=40)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_updates(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        return self

    @field_validator("title", "body")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("shortcut")
    @classmethod
    def normalize_optional_shortcut(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return SavedReplyCreate.normalize_shortcut(value)


class SavedReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    shortcut: str
    body: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
