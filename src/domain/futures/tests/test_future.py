"""Tests for Future VO and futures re-exports."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from domain.futures import Future, FutureChain, FutureContract


def test_future_frozen():
    f = Future(symbol="NIFTY", exchange="NSE", expiry=date(2026, 7, 31), lot_size=50)
    with pytest.raises(FrozenInstanceError):
        f.lot_size = 100  # type: ignore[misc]


def test_future_key():
    f = Future(symbol="NIFTY", exchange="NSE", expiry=date(2026, 7, 31), lot_size=50)
    assert f.key == "NSE:NIFTY:2026-07-31"


def test_future_lot_size_validation():
    with pytest.raises(ValueError, match="lot_size"):
        Future(symbol="X", exchange="BSE", expiry=date(2026, 1, 1), lot_size=0)


def test_future_tick_size_validation():
    with pytest.raises(ValueError, match="tick_size"):
        Future(symbol="X", exchange="BSE", expiry=date(2026, 1, 1), lot_size=1, tick_size=Decimal("-0.1"))


def test_future_is_expired():
    f = Future(symbol="X", exchange="BSE", expiry=date(2020, 1, 1), lot_size=1)
    assert f.is_expired


def test_future_chain_reexport():
    assert FutureChain is not None


def test_future_contract_reexport():
    assert FutureContract is not None
