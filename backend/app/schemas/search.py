from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    kind: Literal["ticket", "customer", "document"]
    id: UUID
    title: str
    subtitle: str
    href: str


class SearchResponse(BaseModel):
    query: str
    items: list[SearchResultOut]
    limit_per_kind: int
