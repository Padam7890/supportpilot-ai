"""Round-robin scheduling state for queue families and tenant pages."""

from collections.abc import Sequence
from uuid import UUID


class FairScheduler:
    """Rotate each dispatch start across tenants and registered job handlers."""

    def __init__(self) -> None:
        self.organization_cursor: UUID | None = None
        self.handler_cursor = 0

    def organizations_after_cursor(self, page: Sequence[UUID]) -> list[UUID]:
        if not page:
            return []
        start = 0
        if self.organization_cursor in page:
            start = (page.index(self.organization_cursor) + 1) % len(page)
        return list(page[start:]) + list(page[:start])

    def handler_indices(self, count: int) -> range:
        return range(self.handler_cursor, self.handler_cursor + count)

    def claimed(self, organization_id: UUID, handler_index: int, handler_count: int) -> None:
        self.organization_cursor = organization_id
        self.handler_cursor = (handler_index + 1) % handler_count

    def checked_organization(self, organization_id: UUID, handler_count: int) -> None:
        self.organization_cursor = organization_id
        self.handler_cursor = (self.handler_cursor + 1) % handler_count

    def reset_page(self) -> None:
        self.organization_cursor = None
