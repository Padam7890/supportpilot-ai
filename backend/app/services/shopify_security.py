"""Deprecated compatibility import; remove after the transition release."""

from app.integrations.providers.shopify import security as _implementation

__all__ = _implementation.__all__


def __getattr__(name: str):
    return getattr(_implementation, name)
