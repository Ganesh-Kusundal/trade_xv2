"""Regression: Dhan order stream maps exchangeSegment to canonical exchange code."""

from __future__ import annotations

from brokers.dhan.websocket.order_stream import DhanOrderStream


def test_transform_order_maps_exchange_segment_to_canonical_code() -> None:
    data = {
        "orderNo": "123",
        "status": "OPEN",
        "tradingSymbol": "RELIANCE",
        "exchangeSegment": "NSE_EQ",
        "transactionType": "BUY",
        "quantity": 1,
        "filledQty": 0,
        "price": "2500",
        "averagePrice": "0",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
    }
    transformed = DhanOrderStream._transform_order(data)
    assert transformed["exchange"] == "NSE"
    assert transformed["exchange"] != "NSE_EQ"
