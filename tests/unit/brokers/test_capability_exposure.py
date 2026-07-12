"""Broker capability matrix exposure via brokers.services."""

from __future__ import annotations

import pytest

from brokers.services import get_capabilities, lookup_instrument


@pytest.mark.unit
def test_paper_capabilities_include_matrix() -> None:
    caps = get_capabilities("paper")
    assert caps["broker_id"] == "paper"
    matrix = caps["matrix"]
    assert isinstance(matrix, dict)
    assert matrix.get("supports_place_order") is True
    assert matrix.get("supports_historical_data") is True
    assert "extensions" in caps
    assert isinstance(caps["extensions"], list)


@pytest.mark.unit
def test_lookup_instrument_has_no_tokens() -> None:
    info = lookup_instrument("paper", "RELIANCE")
    assert info["symbol"] == "RELIANCE"
    assert info["instrument_id"].startswith("NSE:")
    assert "security_id" not in info
    assert "instrument_token" not in info
