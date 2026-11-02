"""Transition facade for existing AI execution imports.

New implementation code belongs under ``app.features.ai``. Keeping these
exports stable preserves callers while the feature module is adopted.
"""

from app.features.ai.infrastructure.checkpoints import (
    CHECKPOINT_SCHEMA,
    CHECKPOINT_SETUP_LOCK,
    CHECKPOINT_TABLES,
    checkpoint_dsn,
    tenant_checkpointer,
)
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    generate_completion,
    is_provider_configured,
)
from app.features.ai.workflows.grounded_reply import (
    ExecutionState,
    build_grounded_draft_graph,
    create_grounded_draft,
)

__all__ = [
    "CHECKPOINT_SCHEMA",
    "CHECKPOINT_SETUP_LOCK",
    "CHECKPOINT_TABLES",
    "AIProviderError",
    "ExecutionState",
    "build_grounded_draft_graph",
    "checkpoint_dsn",
    "create_grounded_draft",
    "generate_completion",
    "is_provider_configured",
    "tenant_checkpointer",
]
