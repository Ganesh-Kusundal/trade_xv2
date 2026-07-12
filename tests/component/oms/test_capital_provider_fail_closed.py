"""ENG-039: GatewayCapitalProvider fail-closed by default."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from application.oms.capital_provider import GatewayCapitalProvider


def test_deferred_init_uses_fallback():
    cp = GatewayCapitalProvider(None, fallback_balance=Decimal("42"), fail_closed=True)
    assert cp.get_available_balance() == Decimal("42")


def test_fail_closed_on_funds_error():
    gw = MagicMock()
    gw.funds.side_effect = RuntimeError("broker down")
    # Wire-style gateway: no ExecutionProvider.get_funds(); prefers .funds().
    del gw.get_funds
    cp = GatewayCapitalProvider(gw, fail_closed=True)
    with pytest.raises(RuntimeError, match="ENG-039"):
        cp.get_available_balance()


def test_fail_open_on_funds_error():
    gw = MagicMock()
    gw.funds.side_effect = RuntimeError("broker down")
    del gw.get_funds
    cp = GatewayCapitalProvider(gw, fallback_balance=Decimal("7"), fail_closed=False)
    assert cp.get_available_balance() == Decimal("7")


def test_funds_ok():
    gw = MagicMock()
    gw.funds.return_value = MagicMock(available_balance=Decimal("1000"))
    del gw.get_funds
    cp = GatewayCapitalProvider(gw, fail_closed=True)
    assert cp.get_available_balance() == Decimal("1000")
