"""Unit tests for PortfolioAdapter.convert_position."""

import pytest

from brokers.providers.dhan.portfolio.portfolio import PortfolioAdapter


def test_convert_position_payload(fake_client, resolver):
    fake_client.set_response("POST", "/positions/convert", {"status": "SUCCESS"})
    adapter = PortfolioAdapter(fake_client, resolver, allow_live_orders=True)

    result = adapter.convert_position(
        "RELIANCE",
        exchange="NSE",
        quantity=40,
        from_product_type="INTRADAY",
        to_product_type="CNC",
        position_type="LONG",
    )

    assert result.get("status") == "SUCCESS"
    payload = fake_client.calls_for("POST", "/positions/convert")[0]
    assert payload["dhanClientId"] == "test"
    assert payload["fromProductType"] == "INTRADAY"
    assert payload["toProductType"] == "CNC"
    assert payload["convertQty"] == 40
    assert payload["positionType"] == "LONG"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["securityId"]  # resolved via identity
    assert payload["tradingSymbol"] == "RELIANCE"


def test_convert_position_with_explicit_security_id(fake_client, resolver):
    fake_client.set_response("POST", "/positions/convert", {})
    adapter = PortfolioAdapter(fake_client, resolver, allow_live_orders=True)

    adapter.convert_position(
        "TCS",
        exchange="NSE",
        quantity=10,
        from_product_type="CNC",
        to_product_type="INTRADAY",
        security_id="11536",
    )
    payload = fake_client.calls_for("POST", "/positions/convert")[0]
    assert payload["securityId"] == "11536"
    assert payload["exchangeSegment"] == "NSE_EQ"


def test_convert_position_rejects_same_product(fake_client, resolver):
    adapter = PortfolioAdapter(fake_client, resolver, allow_live_orders=True)
    with pytest.raises(ValueError, match="must differ"):
        adapter.convert_position(
            "RELIANCE",
            quantity=1,
            from_product_type="INTRADAY",
            to_product_type="intraday",
        )


def test_convert_position_rejects_non_positive_qty(fake_client, resolver):
    adapter = PortfolioAdapter(fake_client, resolver, allow_live_orders=True)
    with pytest.raises(ValueError, match="positive"):
        adapter.convert_position(
            "RELIANCE",
            quantity=0,
            from_product_type="INTRADAY",
            to_product_type="CNC",
        )
