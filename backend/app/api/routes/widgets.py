"""Compatibility exports for the feature-oriented storefront widget routers."""

from app.features.widgets import management_router, public_router
from app.features.widgets.shared import (
    _log_order_verification,
    normalize_origin,
    normalized_origins,
    require_allowed_widget_origin,
    require_visitor_conversation,
    widget_message_out,
    widget_out,
)

__all__ = [
    "_log_order_verification",
    "management_router",
    "normalize_origin",
    "normalized_origins",
    "public_router",
    "require_allowed_widget_origin",
    "require_visitor_conversation",
    "widget_message_out",
    "widget_out",
]
