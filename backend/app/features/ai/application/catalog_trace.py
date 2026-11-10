"""Privacy-safe catalog routing diagnostics with optional LangSmith tracing.

Only boolean flags, counts, route names and execution IDs are emitted.
Never record raw prompts, catalog details, tokens or customer information.
"""
import logging
import os

logger = logging.getLogger(__name__)


def trace_catalog_route(
    *, execution_id: str, route: str, tool: str, follow_up: str | None,
    catalog_request: bool, result_count: int | None = None,
    connection_resolved: bool | None = None,
) -> None:
    event = {
        "execution_id": execution_id,
        "route": route,
        "tool": tool,
        "follow_up": follow_up,
        "catalog_request": catalog_request,
        "result_count": result_count,
        "connection_resolved": connection_resolved,
    }
    logger.info("catalog_routing_debug %s", event)
    if os.getenv("LANGSMITH_TRACING", "").lower() not in {"true", "1"}:
        return
    try:
        from langsmith import traceable
    except ImportError:
        logger.warning("LangSmith tracing enabled but langsmith package is not installed")
        return

    @traceable(name="supportpilot.catalog.routing", run_type="chain")
    def record_diagnostic(data: dict[str, object]) -> dict[str, object]:
        return data

    try:
        record_diagnostic(event)
    except Exception:
        logger.warning("LangSmith catalog diagnostic failed", exc_info=False)
