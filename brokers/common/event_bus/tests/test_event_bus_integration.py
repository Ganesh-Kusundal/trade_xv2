"""Tests for :mod:`brokers.common.event_bus` integration in the OMS.

REF-12: the trading context is the canonical place where the OMS
attaches its handlers to the event bus. If a future revision
breaks one of these subscriptions — by typo or by deleting a
handler — production trading would silently lose updates.

These tests are deliberately exhaustive: every subscription we
expect to be in place is asserted by name. Adding a new
subscription in :class:`TradingContext` requires updating this
list, which forces a corresponding test (and therefore a
reviewer) to acknowledge the change.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.common.event_bus import EventBus, EventType
from brokers.common.oms.context import TradingContext


class TestTradingContextBusSubscriptions:
    """Verify the OMS is wired to every event it claims to consume."""

    def _make_context_with_bus(self) -> tuple[TradingContext, EventBus]:
        """Build a TradingContext and return (ctx, bus)."""
        bus = EventBus()
        ctx = TradingContext(event_bus=bus)
        return ctx, bus

    def test_subscribed_to_order_updated(self):
        _, bus = self._make_context_with_bus()
        assert bus.subscriber_count(EventType.ORDER_UPDATED) >= 1

    def test_subscribed_to_trade(self):
        _, bus = self._make_context_with_bus()
        assert bus.subscriber_count(EventType.TRADE) >= 1

    def test_subscribed_to_trade_applied(self):
        _, bus = self._make_context_with_bus()
        # TRADE_APPLIED has at least one subscriber — the position manager.
        assert bus.subscriber_count(EventType.TRADE_APPLIED) >= 1

    def test_event_types_used_are_canonical(self):
        """All event types the context subscribes to MUST be in
        :data:`EventType`.

        This catches the regression where someone adds a subscription
        using a bare string that is not in the enum. The bus
        accepts arbitrary strings, so a typo would silently go
        unnoticed by the bus itself.
        """
        _, bus = self._make_context_with_bus()
        # Snapshot every subscription the bus has registered.
        canonical_strings = {t.value for t in EventType}
        # We can inspect ``bus._subscribers`` directly — it is a
        # private but stable attribute used by the bus's own tests.
        registered_event_types = set(bus._subscribers.keys())
        unknown = registered_event_types - canonical_strings
        assert not unknown, (
            f"TradingContext subscribes to non-canonical event types: {unknown}; "
            f"add them to EventType in brokers.common.event_bus.event_types"
        )

    def test_subscription_count_is_stable(self):
        """Regression net: the exact number of OMS-owned subscriptions.

        If someone adds a NEW subscription in the constructor
        without updating this test, the failure tells them
        exactly which one they added. The point is not the
        number — it is that the change is explicit.
        """
        _, bus = self._make_context_with_bus()
        # Snapshot the bus after construction (before any
        # user-added subscriptions).
        total = bus.subscriber_count()
        # Three subscriptions: ORDER_UPDATED, TRADE, TRADE_APPLIED
        # (each subscribed exactly once by TradingContext.__init__).
        assert total == 3, (
            f"TradingContext installs {total} subscriptions; expected 3. "
            f"Update this test if you intentionally added one."
        )


class TestBrokerBusTouchpoint:
    """REF-12: broker-specific components take ``event_bus`` via
    constructor injection.

    These tests verify the touchpoint is consistent across the
    two production broker adapters. A future ``BrokersX`` addition
    must follow the same pattern; this test list is the canonical
    checklist.
    """

    @pytest.mark.parametrize(
        "broker_module,class_name,expected_event_types",
        [
            # Each entry: (import path, class name, set of EventTypes
            # that class is EXPECTED to publish during normal operation).
            # The set may be empty (the class never publishes) — that
            # is a valid design choice and we do not flag it here.
            ("brokers.dhan.websocket", "DhanMarketFeed", {EventType.TICK, EventType.DEPTH}),
            ("brokers.dhan.websocket", "DhanOrderStream", {EventType.ORDER_UPDATED, EventType.TRADE}),
            ("brokers.dhan.depth_20", "DhanDepth20Feed", {EventType.DEPTH}),
            ("brokers.dhan.depth_200", "DhanDepth200Feed", {EventType.DEPTH}),
        ],
    )
    def test_broker_component_publishes_canonical_event_types(
        self, broker_module: str, class_name: str, expected_event_types: set[EventType]
    ) -> None:
        """Static contract: the listed broker classes publish only
        event types from :class:`EventType`.

        We do not instantiate the class (most need a live
        connection). Instead we read the source module and grep
        for ``DomainEvent.now(`` call sites, then check that
        every string passed matches an :class:`EventType`.

        This is a coarse check — it does not validate that the
        class publishes EVERY event in the expected set, only
        that what it DOES publish is in the enum.
        """
        import importlib
        import inspect

        module = importlib.import_module(broker_module)
        cls = getattr(module, class_name)
        source = inspect.getsource(cls)

        # Find every DomainEvent.now(...) call. This is a heuristic
        # — a more robust version would walk the AST — but it is
        # adequate for the assertion: we expect every string
        # literal passed to ``DomainEvent.now`` to be a known
        # EventType value.
        canonical_values = {t.value for t in EventType}
        # Quick scan for the strings — we don't need full AST.
        bad: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if "DomainEvent.now(" not in stripped:
                continue
            # Extract first quoted argument
            import re

            m = re.search(r'DomainEvent\.now\(\s*["\']([^"\']+)["\']', stripped)
            if m:
                value = m.group(1)
                if value not in canonical_values:
                    bad.append(value)

        assert not bad, (
            f"{class_name} publishes non-canonical event types: {bad}; "
            f"add them to EventType in brokers.common.event_bus.event_types"
        )
