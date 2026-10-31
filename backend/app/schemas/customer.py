import uuid

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import TimestampedOut


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    external_reference: str | None = Field(default=None, max_length=120)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    external_reference: str | None = Field(default=None, max_length=120)


class CustomerOut(TimestampedOut):
    organization_id: uuid.UUID
    name: str
    email: EmailStr
    phone: str | None
    external_reference: str | None


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    total: int
    limit: int
    offset: int
