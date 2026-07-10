"""Tests for ExchangeSession VO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import time

import pytest

from domain.market import ExchangeSession


def test_frozen():
    s = ExchangeSession(exchange="NSE", segment="CASH", open_time=time(9, 15), close_time=time(15, 30))
    with pytest.raises(FrozenInstanceError):
        s.is_open = True  # type: ignore[misc]


def test_key():
    s = ExchangeSession(exchange="NSE", segment="FNO", open_time=time(9, 15), close_time=time(15, 30))
    assert s.key == "NSE:FNO"


def test_with_open():
    s = ExchangeSession(exchange="BSE", segment="CASH", open_time=time(9, 15), close_time=time(15, 30))
    assert not s.is_open
    opened = s.with_open()
    assert opened.is_open
    assert not s.is_open  # original unchanged


def test_with_closed():
    s = ExchangeSession(exchange="NSE", segment="CASH", open_time=time(9, 15), close_time=time(15, 30), is_open=True)
    closed = s.with_closed()
    assert not closed.is_open
