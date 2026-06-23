"""REF-005: Status normalization contract tests.

Covers:
- Common status strings (OPEN, FILLED, CANCELLED, etc.)
- Broker-specific status strings (Dhan, Upstox variants)
- Idempotency (normalizing already-normalized strings)
- Unknown status strings fall back to OPEN
- Whitespace and case normalization
"""

from __future__ import annotations

import pytest

from domain.status_mapper import StatusMapperRegistry
from domain.types import OrderStatus

# ---------------------------------------------------------------------------
# Common status strings
# ---------------------------------------------------------------------------

class TestCommonStatusNormalization:
    """All common status strings must normalize correctly."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("OPEN", OrderStatus.OPEN),
            ("FILLED", OrderStatus.FILLED),
            ("PARTIALLY_FILLED", OrderStatus.PARTIALLY_FILLED),
            ("CANCELLED", OrderStatus.CANCELLED),
            ("REJECTED", OrderStatus.REJECTED),
            ("EXPIRED", OrderStatus.EXPIRED),
            # Synonyms
            ("EXECUTED", OrderStatus.FILLED),
            ("COMPLETE", OrderStatus.FILLED),
            ("TRADED", OrderStatus.FILLED),
            ("PARTIAL", OrderStatus.PARTIALLY_FILLED),
            ("PARTIALLY_EXECUTED", OrderStatus.PARTIALLY_FILLED),
            ("MARGIN_TRADED", OrderStatus.PARTIALLY_FILLED),
            # Open synonyms
            ("TRANSIT", OrderStatus.OPEN),
            ("TRIGGER_PENDING", OrderStatus.OPEN),
            ("PENDING", OrderStatus.OPEN),
            ("QUEUED", OrderStatus.OPEN),
            ("AMO", OrderStatus.OPEN),
            ("AFTER_MARKET_ORDER_REQ_RECEIVED", OrderStatus.OPEN),
        ],
    )
    def test_common_statuses(self, raw: str, expected: OrderStatus):
        result = StatusMapperRegistry.normalize(raw)
        assert result == expected, f"normalize({raw!r}) should be {expected}, got {result}"


# ---------------------------------------------------------------------------
# Broker-specific registrations
# ---------------------------------------------------------------------------

class TestBrokerSpecificRegistration:
    """Broker adapters can register custom mappings that override common ones."""

    def setup_method(self):
        # Register a test broker mapping
        StatusMapperRegistry.register("test_broker", {
            "PLACED": OrderStatus.OPEN,
            "TRIGGERED": OrderStatus.PARTIALLY_FILLED,
            "SQUARE_OFF": OrderStatus.FILLED,
        })

    def teardown_method(self):
        # Clean up to avoid leaking state into other tests
        StatusMapperRegistry._mappings.pop("test_broker", None)
        StatusMapperRegistry._merged = None

    def test_custom_mapping_works(self):
        result = StatusMapperRegistry.normalize("PLACED")
        assert result == OrderStatus.OPEN

    def test_custom_synonym(self):
        result = StatusMapperRegistry.normalize("SQUARE_OFF")
        assert result == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Normalizing an already-normalized string must return the same result."""

    @pytest.mark.parametrize("status", list(OrderStatus))
    def test_idempotent_on_enum_names(self, status: OrderStatus):
        first = StatusMapperRegistry.normalize(status.value)
        second = StatusMapperRegistry.normalize(status.value)
        assert first == second

    def test_double_normalize_filled(self):
        assert StatusMapperRegistry.normalize("FILLED") == OrderStatus.FILLED
        assert StatusMapperRegistry.normalize("FILLED") == OrderStatus.FILLED


# ---------------------------------------------------------------------------
# Unknown status fallback
# ---------------------------------------------------------------------------

class TestUnknownStatusFallback:
    """Unknown status strings must fall back to OPEN (DM-009 contract)."""

    @pytest.mark.parametrize(
        "raw",
        [
            "UNKNOWN_STATUS",
            "BOGUS",
            "42",
            "",
            "GATEWAY_TIMEOUT",
            "UNKNOWN_REJECTED",
        ],
    )
    def test_unknown_falls_back_to_open(self, raw: str):
        result = StatusMapperRegistry.normalize(raw)
        assert result == OrderStatus.OPEN, (
            f"normalize({raw!r}) should fall back to OPEN, got {result}"
        )


# ---------------------------------------------------------------------------
# Normalization rules
# ---------------------------------------------------------------------------

class TestNormalizationRules:
    """Status strings are uppercased, stripped, and spaces→underscores."""

    def test_lowercase_input(self):
        assert StatusMapperRegistry.normalize("filled") == OrderStatus.FILLED

    def test_mixed_case(self):
        assert StatusMapperRegistry.normalize("Partially_Filled") == OrderStatus.PARTIALLY_FILLED

    def test_whitespace_around(self):
        assert StatusMapperRegistry.normalize("  CANCELLED  ") == OrderStatus.CANCELLED

    def test_spaces_to_underscores(self):
        assert StatusMapperRegistry.normalize("PARTIALLY FILLED") == OrderStatus.PARTIALLY_FILLED

    def test_mixed_whitespace_and_case(self):
        assert StatusMapperRegistry.normalize("  partially filled  ") == OrderStatus.PARTIALLY_FILLED
