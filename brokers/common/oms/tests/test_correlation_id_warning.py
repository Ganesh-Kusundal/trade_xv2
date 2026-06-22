"""Unit tests for the OmsOrderCommand correlation_id deprecation warning.

Plan §7 + §4.6 #9: a ``correlation_id`` that is ``None`` silently disables
OMS idempotency because every call gets a fresh UUID. PR 1 keeps the
auto-UUID for backward compatibility but emits a ``DeprecationWarning``
so the gap is visible in any test or production log.
"""

from __future__ import annotations

import warnings

from brokers.common.core.domain import Side
from brokers.common.oms.order_manager import OmsOrderCommand


class TestCorrelationIdDeprecation:
    def test_no_correlation_id_emits_deprecation_warning(self) -> None:
        """Constructing without correlation_id must warn so the gap is visible."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cmd = OmsOrderCommand(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
            )
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecation_warnings, (
            "OmsOrderCommand without correlation_id must emit a DeprecationWarning; "
            "silent auto-UUID disables place-order idempotency."
        )
        # The auto-UUID fallback must still kick in for backward compatibility.
        assert cmd.correlation_id, "fallback correlation_id must be set"
        assert cmd.correlation_id.startswith("ord:")

    def test_explicit_correlation_id_does_not_warn(self) -> None:
        """When the caller supplies correlation_id, no warning is emitted."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cmd = OmsOrderCommand(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                correlation_id="ord:abc-123",
            )
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert not deprecation_warnings, (
            "OmsOrderCommand with explicit correlation_id must NOT warn; "
            "the auto-UUID path was not taken."
        )
        assert cmd.correlation_id == "ord:abc-123"

    def test_explicit_empty_string_triggers_auto_and_warns(self) -> None:
        """An empty string is treated as missing — same warning, same fallback."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cmd = OmsOrderCommand(
                symbol="RELIANCE",
                exchange="NSE",
                side=Side.BUY,
                quantity=10,
                correlation_id="",
            )
        deprecation_warnings = [
            w for w in caught if issubclass(w.category, DeprecationWarning)
        ]
        assert deprecation_warnings
        assert cmd.correlation_id.startswith("ord:")
