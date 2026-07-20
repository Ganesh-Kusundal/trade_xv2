"""Shared mock helpers for Dhan SDK classes.

Centralizes the mock patching of _sdk_market_feed_class and
_sdk_order_update_class so that a rename in product code only
requires updating this one file.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

# All known import locations for _sdk_market_feed_class.
# Patching at the source alone is not enough: modules that do
# ``from _helpers import _sdk_market_feed_class`` bind a local
# reference at import time, so we must also patch those bindings.
_FEED_PATCH_TARGETS = [
    "brokers.dhan.websocket._helpers._sdk_market_feed_class",
    "brokers.dhan.websocket.connection._sdk_market_feed_class",
]

_ORDER_PATCH_TARGETS = [
    "brokers.dhan.websocket._helpers._sdk_order_update_class",
    "brokers.dhan.websocket.order_stream._sdk_order_update_class",
]


@contextmanager
def mock_market_feed_class() -> Iterator[MagicMock]:
    """Patch the SDK MarketFeed class at all known import locations.

    Usage in tests::

        with mock_market_feed_class() as MockFeed:
            MockFeed.return_value.some_method.return_value = ...
    """
    with ExitStack() as stack:
        mocks = [stack.enter_context(patch(target)) for target in _FEED_PATCH_TARGETS]
        # All patches target the same object — yield the first (source) mock.
        yield mocks[0]


@contextmanager
def mock_order_update_class() -> Iterator[MagicMock]:
    """Patch the SDK OrderUpdate class at all known import locations."""
    with ExitStack() as stack:
        mocks = [stack.enter_context(patch(target)) for target in _ORDER_PATCH_TARGETS]
        yield mocks[0]


@contextmanager
def mock_both_sdk_classes() -> Iterator[tuple[MagicMock, MagicMock]]:
    """Patch both SDK classes simultaneously at all known import locations."""
    with ExitStack() as stack:
        feed_mocks = [stack.enter_context(patch(t)) for t in _FEED_PATCH_TARGETS]
        order_mocks = [stack.enter_context(patch(t)) for t in _ORDER_PATCH_TARGETS]
        yield feed_mocks[0], order_mocks[0]
