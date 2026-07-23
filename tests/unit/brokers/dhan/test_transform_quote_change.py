"""Tests for streaming quote ``change`` computation.

Guards the contract drift where ``_transform_quote`` hardcoded
``change = 0`` while the REST path returns a real ``net_change``. The
streaming frame carries the previous ``close``, so day change is derived
as ``ltp - close`` to keep parity with REST.
"""

from __future__ import annotations

from decimal import Decimal

from brokers.providers.dhan.websocket._helpers import _transform_quote


def test_transform_quote_computes_change_from_close():
    result = _transform_quote({"security_id": "2885", "last_price": 105.0, "close": 100.0})
    assert result["change"] == Decimal("5.0")


def test_transform_quote_change_zero_when_close_missing():
    result = _transform_quote({"security_id": "2885", "last_price": 105.0})
    assert result["change"] == Decimal("0")


def test_transform_quote_change_zero_when_close_zero():
    result = _transform_quote({"security_id": "2885", "last_price": 105.0, "close": 0})
    assert result["change"] == Decimal("0")
