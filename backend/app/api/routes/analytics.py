"""Compatibility exports for analytics endpoints and helpers."""

from app.features.analytics import router
from app.features.analytics.router import date_window

__all__ = ["date_window", "router"]
