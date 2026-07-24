"""Gateway auto-loads the instrument master on first call (no network).

Mirrors the token-style convenience: callers must never have to remember to
call ``load_instruments()`` before ``ltp``/``get_quote``/``place_order``.
Exercises the gateway -> connection ``ensure_fresh`` single-flight seam with a
fake connection, so the test runs offline and deterministic.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any
from uuid import uuid4

from domain.commands import PlaceOrderCommand
from domain.enums import OrderSide, OrderType, TimeInForce
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    OrderId,
    Price,
    Quantity,
)


class _FakeConnection:
    """Records ensure_fresh/load_instruments calls; no I/O."""

    def __init__(self) -> None:
        self.ensure_fresh_calls = 0
        self.load_instruments_calls = 0
        self._instruments_loaded = False
        self._instruments_lock = threading.Lock()
        self.allow_live_orders = True
        self.orders = self
        self.market_data = self

    def connect(self) -> None:
        # no-op for the fake; real connection starts the token + instrument schedulers
        pass

    def ensure_fresh(self, *, force_refresh: bool = False) -> None:
        self.ensure_fresh_calls += 1
        if not force_refresh and self._instruments_loaded:
            return
        with self._instruments_lock:
            if not force_refresh and self._instruments_loaded:
                return
            self.load_instruments()
            self._instruments_loaded = True

    def load_instruments(self) -> None:
        self.load_instruments_calls += 1

    def get_ltp(self, instrument_id: InstrumentId) -> Price:
        return Price(value=Decimal("0"))

    def place_order(self, command: PlaceOrderCommand) -> OrderId:
        return OrderId(value="ORD1")


def _make_gateway(connection: _FakeConnection) -> Any:
    """Build a minimal gateway-like object with the new ensure_fresh seam."""

    class _Gateway:
        def __init__(self, conn: _FakeConnection) -> None:
            self.connection = conn

        def connect(self) -> None:
            self.connection.connect()
            self.ensure_fresh()

        def ensure_fresh(self, *, force_refresh: bool = False) -> None:
            self.connection.ensure_fresh(force_refresh=force_refresh)

        def ltp(self, instrument_id: InstrumentId) -> Price:
            self.ensure_fresh()
            return self.connection.market_data.get_ltp(instrument_id)

        def place_order(self, command: PlaceOrderCommand) -> OrderId:
            self.ensure_fresh()
            return self.connection.orders.place_order(command)

    return _Gateway(connection)


def _sample_order_cmd() -> PlaceOrderCommand:
    return PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Quantity(value=Decimal("1")),
        price=None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


def test_first_ltp_triggers_single_load() -> None:
    conn = _FakeConnection()
    gw = _make_gateway(conn)

    assert conn.load_instruments_calls == 0

    gw.ltp(InstrumentId.parse("NSE:RELIANCE"))
    gw.ltp(InstrumentId.parse("NFO:NIFTY:20260730:FUT"))
    gw.ltp(InstrumentId.parse("MCX:CRUDEOIL"))

    # Only the FIRST call downloads; the rest are no-ops (single-flight).
    assert conn.load_instruments_calls == 1
    assert conn.ensure_fresh_calls == 3


def test_force_refresh_reloads() -> None:
    conn = _FakeConnection()
    gw = _make_gateway(conn)

    gw.ltp(InstrumentId.parse("NSE:RELIANCE"))
    assert conn.load_instruments_calls == 1

    gw.ensure_fresh(force_refresh=True)
    assert conn.load_instruments_calls == 2


def test_connect_triggers_proactive_first_load() -> None:
    conn = _FakeConnection()
    gw = _make_gateway(conn)

    # connect() must warm the master eagerly (no gateway call yet).
    gw.connect()
    assert conn.load_instruments_calls == 1

    # A later ltp() should NOT reload (single-flight).
    gw.ltp(InstrumentId.parse("NSE:RELIANCE"))
    assert conn.load_instruments_calls == 1
    assert conn.ensure_fresh_calls == 2


def test_capabilities_reflect_mcx_and_commodity() -> None:
    """Capabilities must mirror the real wire surface (NSE/MCX equity+deriv+commodity)."""
    from domain.enums import AssetClass

    dhan = __import__(
        "plugins.brokers.dhan.gateway", fromlist=["DHAN_CAPABILITIES"]
    ).DHAN_CAPABILITIES
    upstox = __import__(
        "plugins.brokers.upstox.gateway", fromlist=["UPSTOX_CAPABILITIES"]
    ).UPSTOX_CAPABILITIES

    for caps in (dhan, upstox):
        assert AssetClass.COMMODITY in caps.supported_asset_classes
        assert AssetClass.DERIVATIVE in caps.supported_asset_classes
        assert AssetClass.EQUITY in caps.supported_asset_classes
        assert AssetClass.CURRENCY in caps.supported_asset_classes

