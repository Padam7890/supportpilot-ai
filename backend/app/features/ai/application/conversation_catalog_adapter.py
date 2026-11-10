"""Read-only tenant-scoped catalog adapter for agent tool execution."""

from collections.abc import Callable
from uuid import UUID

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.catalog_search import load_candidates
from app.features.ai.application.conversation_tool_contracts import (
    ToolName, ToolRequest, ToolResult,
)
from app.features.ai.domain.catalog import _terms


def build_catalog_search_adapter(*, organization_id: UUID) -> Callable:
    async def search(request: ToolRequest) -> ToolResult:
        if request.name != ToolName.CATALOG_SEARCH:
            raise ValueError("Catalog adapter received a different tool")
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            candidates, _, _ = await load_candidates(db, organization_id, request.query)
        # load_candidates may return a whole-catalog fallback on no text hit.
        # Never present unrelated products as matching the requested item.
        terms = set(_terms(request.query))
        matching = [
            candidate for candidate in candidates
            if terms and any(term in candidate.searchable_text for term in terms)
        ][:6]
        facts: list[str] = []
        source_ids: list[str] = []
        for candidate in matching:
            product, variant = candidate.product, candidate.variant
            facts.append(
                f"Product: {str(product.title)[:180]}; "
                f"Brand: {str(product.brand or 'unspecified')[:100]}; "
                f"Variant: {str(variant.title or 'default')[:100]}; "
                f"Availability: {str(variant.availability)[:40]}"
            )
            source_ids.append(str(product.id))
        return ToolResult(
            name=ToolName.CATALOG_SEARCH,
            status="ok" if facts else "not_found",
            facts=facts,
            source_ids=source_ids,
        )

    return search
