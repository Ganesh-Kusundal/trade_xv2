"""Tests for enforce_gateway_capabilities — fail-closed on capability mismatch.

validate_gateway_capabilities() itself is a pure check (never raises) and is
covered elsewhere (tests/regression/test_remediation_common_marketdata.py).
This file covers the enforcing wrapper added to close the previously-soft
"capability lie" gap: a mismatch must abort gateway construction, not just
log a warning.
"""

from __future__ import annotations

import pytest

from brokers.common.capabilities_validator import (
    CapabilityMismatchError,
    enforce_gateway_capabilities,
)


class _Caps:
    supports_modify_order = True


class _MismatchedGateway:
    """Advertises supports_modify_order but has no modify_order method."""

    def capabilities(self) -> _Caps:
        return _Caps()


class _ConsistentGateway:
    """Advertises supports_modify_order and actually has the method."""

    def capabilities(self) -> _Caps:
        return _Caps()

    def modify_order(self) -> None:
        pass


def test_enforce_raises_on_mismatch() -> None:
    with pytest.raises(CapabilityMismatchError) as exc_info:
        enforce_gateway_capabilities(_MismatchedGateway())
    assert "supports_modify_order" in str(exc_info.value)
    assert "_MismatchedGateway" in str(exc_info.value)


def test_enforce_is_silent_when_consistent() -> None:
    enforce_gateway_capabilities(_ConsistentGateway())  # must not raise


class _HistoricalCaps:
    supports_historical_data = True


class _NoHistoryGateway:
    def capabilities(self) -> _HistoricalCaps:
        return _HistoricalCaps()


class _HistoryGateway:
    def capabilities(self) -> _HistoricalCaps:
        return _HistoricalCaps()

    def history(self, *args, **kwargs):
        return None


def test_enforce_raises_when_historical_data_unbacked() -> None:
    with pytest.raises(CapabilityMismatchError) as exc_info:
        enforce_gateway_capabilities(_NoHistoryGateway())
    assert "supports_historical_data" in str(exc_info.value)


def test_enforce_passes_when_history_present() -> None:
    enforce_gateway_capabilities(_HistoryGateway())
