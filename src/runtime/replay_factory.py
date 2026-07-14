"""Composition-root registry for the replay TradingContext factory.

analytics.replay.orchestrator cannot import application.oms (layering
boundary), so the wiring concern of "how to build a TradingContext" lives
here in the composition root. The application startup registers the
canonical ``application.oms.factory.create_trading_context``; the
orchestrator reads it via :func:`get_trading_context_factory`.

This moves the registry OUT of ``domain.runtime_hooks`` (which must stay
pure) — see audit REF-6.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


_trading_context_factory: Callable[..., Any] | None = None


def set_trading_context_factory(factory: Callable[..., Any]) -> None:
    """Register the canonical TradingContext builder (call at composition root)."""
    global _trading_context_factory
    _trading_context_factory = factory


def get_trading_context_factory() -> Callable[..., Any] | None:
    """Return the registered TradingContext factory, or None if not set."""
    return _trading_context_factory
