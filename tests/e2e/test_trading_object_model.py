"""Epic 2 — Trading object-model E2E (paper CI gate).

Slices:
  TR-020  buy / sell / modify / cancel via Instrument + Session
  TR-021  positions + funds after paper market fill
  TR-023  correlation_id idempotency (same id → same order_id)
  fail-closed: mode=market raises ORDERS_DISABLED

Product path::

    BrokerSession.connect("paper")
      → universe.equity → buy/market/sell/modify/cancel
      → account.refresh → positions / funds
"""

from __future__ import annotations

from brokers import BrokerSession
from tests.support.gateway_orders import (
    cancel_via_gateway,
    modify_via_gateway,
    place_via_gateway,
    subscribe_via_gateway,
)

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import tradex
from domain.enums import OrderStatus
from domain.value_objects.price import snap_to_tick


def _status_value(order) -> str:
    st = getattr(order, "status", None)
    if st is None:
        return ""
    return st.value if hasattr(st, "value") else str(st)


def _dec(value) -> Decimal:
    """Money / Decimal / numeric → Decimal for assertions."""
    if value is None:
        return Decimal("0")
    if hasattr(value, "to_decimal"):
        return value.to_decimal()
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _domain_session(session):
    return getattr(session, "session", session)


def _tick_aligned_limit(stock, multiple: Decimal = Decimal("2")) -> Decimal:
    """Build a tick-aligned LIMIT price from LTP (risk rejects unaligned prices)."""
    raw = _dec(getattr(stock, "ltp", None) or Decimal("1000")) * multiple
    tick = _dec(getattr(stock, "tick_size", None) or Decimal("0.05"))
    return snap_to_tick(raw, tick)


# ── TR-020: buy / sell / modify / cancel ────────────────────────────────


def test_tr020_instrument_limit_buy_stays_open() -> None:
    """Instrument LIMIT buy far below market remains OPEN on paper."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        result = place_via_gateway(session, stock, 
            1,
            price=Decimal("1"),
            correlation_id="e2e:tr020:limit-open",
        )
        assert result.success is True
        assert result.order is not None
        assert result.order.order_id
        assert _status_value(result.order) == OrderStatus.OPEN.value
        assert result.order.quantity == 1
        assert _dec(result.order.price) == Decimal("1")
    finally:
        session.close()


def test_tr020_session_market_buy_fills() -> None:
    """session.market BUY fills immediately on paper."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        result = place_via_gateway(session, stock, 2, side="BUY", order_type="MARKET")
        assert result.success is True
        assert result.order is not None
        assert result.order.order_id
        assert _status_value(result.order) == OrderStatus.FILLED.value
        assert result.order.filled_quantity == 2
        assert result.order.quantity == 2
    finally:
        session.close()


def test_tr020_session_sell_places_order() -> None:
    """session.sell places a SELL order successfully (LIMIT may stay OPEN)."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("INFY")
        # Establish a long so sell is meaningful if risk checks apply
        buy = place_via_gateway(session, stock, 3, side="BUY", order_type="MARKET")
        assert buy.success is True

        stock.refresh()
        # Price must stay within risk notional bounds (extreme limits are rejected)
        limit_px = _tick_aligned_limit(stock)
        result = place_via_gateway(session, stock, 1, price=limit_px, side="SELL")
        assert result.success is True, getattr(result, "error", None)
        assert result.order is not None
        assert result.order.order_id
        assert str(getattr(result.order, "side", "")).upper().endswith("SELL")
    finally:
        session.close()


def test_tr020_cancel_open_order() -> None:
    """session.cancel cancels an OPEN limit order."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("TCS")
        placed = place_via_gateway(session, stock, 
            1,
            price=Decimal("1"),
            correlation_id="e2e:tr020:cancel",
        )
        assert placed.success is True
        oid = placed.order.order_id
        assert _status_value(placed.order) == OrderStatus.OPEN.value

        cancelled = cancel_via_gateway(session, oid)
        assert cancelled.success is True
        assert cancelled.order is not None
        assert _status_value(cancelled.order) == OrderStatus.CANCELLED.value
    finally:
        session.close()


def test_tr020_modify_price_then_cancel() -> None:
    """session.modify updates limit price; subsequent cancel succeeds."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        placed = place_via_gateway(session, stock, 
            1,
            price=Decimal("1"),
            correlation_id="e2e:tr020:modify",
        )
        assert placed.success is True
        oid = placed.order.order_id

        new_price = Decimal("2")
        modified = modify_via_gateway(session, oid, price=new_price)
        assert modified.success is True, getattr(modified, "error", None)
        assert modified.order is not None
        assert _dec(modified.order.price) == new_price
        assert _status_value(modified.order) == OrderStatus.OPEN.value

        cancelled = cancel_via_gateway(session, oid)
        assert cancelled.success is True
        assert _status_value(cancelled.order) == OrderStatus.CANCELLED.value
    finally:
        session.close()


def test_tr020_full_order_lifecycle_slice() -> None:
    """TR-020 combined: limit OPEN → market FILL → sell → modify → cancel."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")

        limit_r = place_via_gateway(session, stock, 1, price=Decimal("1"), correlation_id="e2e:tr020:life:limit")
        assert limit_r.success and _status_value(limit_r.order) == OrderStatus.OPEN.value
        open_id = limit_r.order.order_id

        mkt = place_via_gateway(session, stock, 2, side="BUY", order_type="MARKET")
        assert mkt.success and _status_value(mkt.order) == OrderStatus.FILLED.value

        stock.refresh()
        sell_px = _tick_aligned_limit(stock)
        sell_r = place_via_gateway(session, stock, 1, price=sell_px, side="SELL")
        assert sell_r.success is True, getattr(sell_r, "error", None)

        mod = modify_via_gateway(session, open_id, price=Decimal("3"))
        assert mod.success is True
        assert _dec(mod.order.price) == Decimal("3")

        can = cancel_via_gateway(session, open_id)
        assert can.success is True
        assert _status_value(can.order) == OrderStatus.CANCELLED.value
    finally:
        session.close()


# ── TR-021: positions + funds after fill ────────────────────────────────


def test_tr021_account_positions_after_market_fill() -> None:
    """After market fill, account.refresh() exposes position + funds."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        qty = 2
        fill = place_via_gateway(session, stock, qty, side="BUY", order_type="MARKET")
        assert fill.success is True
        assert _status_value(fill.order) == OrderStatus.FILLED.value

        view = session.account.refresh()
        assert view is session.account
        assert view.is_refreshed is True

        # positions is a property (list), not callable
        positions = session.account.positions
        assert isinstance(positions, list)
        assert len(positions) >= 1

        match = [p for p in positions if str(getattr(p, "symbol", "")).upper() == "RELIANCE"]
        assert match, f"expected RELIANCE in positions, got {positions!r}"
        pos = match[0]
        assert int(getattr(pos, "quantity", 0)) >= qty

        funds = session.account.funds
        assert funds is not None
        # Balance-like object or dict with available capital
        available = getattr(funds, "available_balance", None)
        if available is None and isinstance(funds, dict):
            available = funds.get("available_balance")
        assert available is not None
    finally:
        session.close()


def test_tr021_portfolio_reflects_position() -> None:
    """AccountView.portfolio tracks at least one position after fill."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("INFY")
        assert place_via_gateway(session, stock, 1, side="BUY", order_type="MARKET").success is True

        session.account.refresh()
        portfolio = session.account.portfolio
        assert portfolio.position_count >= 1
        desc = session.account.describe()
        assert desc["refreshed"] is True
        assert desc["position_count"] >= 1
        assert desc["has_funds"] is True
    finally:
        session.close()


# ── TR-023: correlation_id idempotency ──────────────────────────────────


def test_tr023_same_correlation_id_same_order_id() -> None:
    """Placing twice with the same correlation_id returns the same order_id."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("RELIANCE")
        cid = "e2e:tr023:idempotent-1"
        ds = _domain_session(session)
        intent = ds.intent(
            stock,
            "BUY",
            1,
            price=Decimal("100"),
            correlation_id=cid,
        )
        r1 = ds.place(intent)
        r2 = ds.place(intent)

        assert r1.success is True
        assert r2.success is True
        assert r1.order is not None and r2.order is not None
        assert r1.order.order_id == r2.order.order_id
        assert r1.order.correlation_id == cid or r1.order.correlation_id is not None
    finally:
        session.close()


def test_tr023_instrument_buy_idempotent_correlation_id() -> None:
    """gateway place_order with same correlation_id is idempotent via OMS."""
    session = BrokerSession.connect("paper")
    try:
        stock = session.universe.equity("TCS")
        cid = "e2e:tr023:inst-buy"
        r1 = place_via_gateway(session, stock, 1, price=Decimal("50"), correlation_id=cid)
        r2 = place_via_gateway(session, stock, 1, price=Decimal("50"), correlation_id=cid)
        assert r1.success and r2.success
        assert r1.order.order_id == r2.order.order_id
    finally:
        session.close()


# ── Fail closed: mode=market ────────────────────────────────────────────


def test_market_mode_orders_disabled() -> None:
    """mode=market has no OMS; buy / cancel / modify raise ORDERS_DISABLED."""
    mock_gw = MagicMock(name="DhanGateway")

    with patch("infrastructure.gateway.factory._create_transport_gateway", return_value=mock_gw):
        import brokers.providers.dhan  # noqa: F401

        session = tradex.connect("dhan", mode="market", load_instruments=False)
        try:
            assert session.status is not None
            assert session.status.mode == "market"
            assert session.status.orders_enabled is False
            assert session.order_service is None

            stock = session.universe.equity("RELIANCE")
            with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
                place_via_gateway(session, stock, 1, price=Decimal("100"))
            with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
                cancel_via_gateway(session, "fake-id")
            with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
                modify_via_gateway(session, "fake-id", price=Decimal("101"))

            from domain.errors import NotConfiguredError

            with pytest.raises((RuntimeError, NotConfiguredError), match="ORDERS_DISABLED"):
                place_via_gateway(session, stock, 1, price=Decimal("100"))
        finally:
            session.close()
