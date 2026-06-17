"""Tests for :mod:`brokers.common.event_bus.event_types` (REF-11).

These tests guard the contract:

- Every :class:`EventType` is reachable as both enum and string.
- :data:`canonical_event_types` is the single source of truth for
  what the bus considers valid.
- :func:`make_payload` validates required keys when asked.
"""
from __future__ import annotations

import pytest

from brokers.common.event_bus.event_types import (
    EVENT_PAYLOADS,
    EventType,
    canonical_event_types,
    make_payload,
)


class TestEventType:
    def test_str_compatibility(self):
        """EventType is str-backed; legacy ``== "TICK"`` comparisons work."""
        assert EventType.TICK == "TICK"
        assert EventType.TICK.value == "TICK"

    def test_distinct_values(self):
        values = {t.value for t in EventType}
        assert len(values) == len(list(EventType)), "duplicate EventType values"

    def test_canonical_event_types_includes_enum_values(self):
        canonical = canonical_event_types()
        for t in EventType:
            assert t.value in canonical

    def test_canonical_event_types_is_frozenset(self):
        canonical = canonical_event_types()
        assert isinstance(canonical, frozenset)


class TestPayloadContracts:
    def test_event_payloads_covers_known_event_types(self):
        # Every event type used in production must have a contract
        # entry — even if the contract is "no required keys". This
        # test fails fast when someone adds an EventType but
        # forgets to update EVENT_PAYLOADS.
        for event_type in EventType:
            assert event_type in EVENT_PAYLOADS, (
                f"{event_type.value} has no EventPayload entry — "
                f"add one to EVENT_PAYLOADS in event_types.py"
            )

    def test_tick_has_no_required_keys(self):
        # TICK is the highest-volume event; if we required keys
        # here, every quote snapshot would need validation. The
        # contract is "best effort" — subscribers handle missing
        # optional keys gracefully.
        contract = EVENT_PAYLOADS[EventType.TICK]
        assert contract.required_keys == ()

    def test_trade_requires_trade_field(self):
        contract = EVENT_PAYLOADS[EventType.TRADE]
        assert "trade" in contract.required_keys


class TestMakePayload:
    def test_passthrough_when_not_validating(self):
        payload = {"anything": "goes"}
        assert make_payload(EventType.TICK, payload, validate=False) is payload

    def test_validation_passes_when_required_keys_present(self):
        payload = {"order_id": "O1", "reason": "insufficient_funds"}
        out = make_payload(EventType.ORDER_REJECTED, payload, validate=True)
        assert out is payload

    def test_validation_raises_on_missing_required_key(self):
        payload = {"reason": "boom"}  # missing order_id
        with pytest.raises(KeyError, match="ORDER_REJECTED"):
            make_payload(EventType.ORDER_REJECTED, payload, validate=True)

    def test_validation_skipped_for_unknown_event_type(self):
        # Forward-compat: an EventType not yet in EVENT_PAYLOADS is
        # allowed without raising. The bus should never block new
        # event types just because the contract table is stale.
        class _PhantomType(str):
            pass

        phantom = _PhantomType("PHANTOM")
        payload = {"x": 1}
        assert make_payload(phantom, payload, validate=True) is payload

    def test_validation_passes_when_no_required_keys(self):
        # TICK has no required keys — even an empty payload is valid.
        assert make_payload(EventType.TICK, {}, validate=True) == {}


class TestStrEnumBehaviour:
    """Confirm EventType behaves like a string for hashing and dict keys.

    This is a regression net: if someone later drops the ``str``
    parent class, dictionary lookups with string keys will silently
    break — exactly the failure mode that prompted REF-11.
    """

    def test_dict_lookup_with_string_value(self):
        mapping = {EventType.TICK: "T-data", EventType.TRADE: "T-trade"}
        assert mapping["TICK"] == "T-data"
        assert mapping["TRADE"] == "T-trade"

    def test_can_be_serialised_to_json(self):
        import json

        # str-backed enums serialise naturally — if the parent class
        # ever changes, this test will break loudly instead of
        # silently producing dicts in production logs.
        assert json.dumps(EventType.TICK) == '"TICK"'
