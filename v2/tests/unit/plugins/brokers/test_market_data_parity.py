"""Regression tests for market-data parity fixes (v2 vs legacy src).

Covers:
- Upstox ``response_key`` fix: quote/ltp responses are keyed by
  ``EXCHANGE:SYMBOL`` (colon), not by the registered ``instrument_key``
  (``EXCHANGE|ISIN``).
- Dhan columnar history parsing: ``/charts/historical`` and ``/charts/intraday``
  return ``{"open":[...],"high":[...],"timestamp":[...]}`` (dict of arrays),
  not a list of row dicts.
- Dhan depth extensions delegate to the streaming adapter's ``stream_depth``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.commands import PlaceOrderCommand
from domain.entities import DepthLevel, MarketDepth
from domain.enums import OrderSide, OrderType, ProductType, TimeInForce
from domain.value_objects import CorrelationId, InstrumentId, Price, Quantity, TimeFrame
from plugins.brokers.dhan.adapters.market_data import DhanMarketDataAdapter
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.dhan.extensions import DhanDepth20Extension
from plugins.brokers.upstox.adapters.market_data import UpstoxMarketDataAdapter
from plugins.brokers.upstox.wire import UpstoxWire


class _FakeTransport:
    """Records calls; returns canned responses per path.

    Implements the ``BaseTransport`` protocol surface used by the adapters
    (get/post are required; put/delete are unused here).
    """

    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("POST", path, kwargs))
        return self._responses.get(path, {})

    def get(self, path: str, **kwargs: Any) -> Any:
        self.calls.append(("GET", path, kwargs))
        return self._responses.get(path, {})

    def put(self, path: str, **kwargs: Any) -> Any:  # pragma: no cover - unused
        self.calls.append(("PUT", path, kwargs))
        return {}

    def delete(self, path: str, **kwargs: Any) -> Any:  # pragma: no cover - unused
        self.calls.append(("DELETE", path, kwargs))
        return {}


# ---------------------------------------------------------------------------
# Upstox response_key fix
# ---------------------------------------------------------------------------


def test_upstox_response_key_uses_colon_symbol_not_instrument_key() -> None:
    wire = UpstoxWire()
    # Register the real instrument_key (pipe + ISIN) — the bug was looking up
    # the response by this value.
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    # The quote/ltp response is keyed by EXCHANGE:SYMBOL (colon + symbol).
    assert wire.response_key(InstrumentId.parse("NSE:RELIANCE")) == "NSE_EQ:RELIANCE"


def test_upstox_to_ltp_uses_response_key() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    native = {"status": "success", "data": {"NSE_EQ:RELIANCE": {"last_price": 1272.2}}}
    price = wire.to_ltp(native, instrument_id=InstrumentId.parse("NSE:RELIANCE"))
    assert price.value == Decimal("1272.2")


def test_upstox_get_ltp_end_to_end() -> None:
    transport = _FakeTransport(
        {
            "/market-quote/ltp": {
                "status": "success",
                "data": {"NSE_EQ:RELIANCE": {"last_price": 1272.2}},
            }
        }
    )
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    adapter = UpstoxMarketDataAdapter(transport=transport, wire=wire)
    price = adapter.get_ltp(InstrumentId.parse("NSE:RELIANCE"))
    assert price.value == Decimal("1272.2")
    # Confirm the request used the instrument_key (pipe form), not response_key.
    _, _, kwargs = transport.calls[0]
    assert kwargs["params"]["instrument_key"] == "NSE_EQ|INE002A01018"


# ---------------------------------------------------------------------------
# Dhan columnar history parsing
# ---------------------------------------------------------------------------


def _dhan_wire() -> DhanWire:
    wire = DhanWire()
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    return wire


def test_dhan_history_daily_columnar() -> None:
    # Dhan daily historical returns a *columnar* dict, not a list of rows.
    transport = _FakeTransport(
        {
            "/charts/historical": {
                "open": [1317.2, 1321.0],
                "high": [1345.9, 1326.9],
                "low": [1314.9, 1302.7],
                "close": [1323.1, 1303.7],
                "volume": [14305844.0, 12753410.0],
                "timestamp": [1710000000, 1710086400],
            }
        }
    )
    adapter = DhanMarketDataAdapter(transport=transport, wire=_dhan_wire())
    bars = adapter.get_history(
        InstrumentId.parse("NSE:RELIANCE"),
        TimeFrame(value="day"),
        datetime(2024, 3, 9),
        datetime(2024, 3, 10),
    )
    assert len(bars) == 2
    assert bars[0].open.value == Decimal("1317.2")
    assert bars[0].close.value == Decimal("1323.1")
    assert bars[0].volume.value == Decimal("14305844")
    # timestamp decoded from epoch seconds
    assert bars[0].timestamp == datetime.fromtimestamp(1710000000)


def test_dhan_history_intraday_columnar() -> None:
    transport = _FakeTransport(
        {
            "/charts/intraday": {
                "open": [1283.0, 1281.2],
                "high": [1285.0, 1283.0],
                "low": [1280.8, 1281.0],
                "close": [1284.0, 1282.0],
                "volume": [1000.0, 2000.0],
                "timestamp": [1710000000, 1710000300],
            }
        }
    )
    adapter = DhanMarketDataAdapter(transport=transport, wire=_dhan_wire())
    bars = adapter.get_history(
        InstrumentId.parse("NSE:RELIANCE"),
        TimeFrame(value="5m"),
        datetime(2024, 3, 9, 9, 15),
        datetime(2024, 3, 9, 15, 30),
    )
    assert len(bars) == 2
    assert bars[1].close.value == Decimal("1282.0")


def test_dhan_history_uses_iso_date_format() -> None:
    transport = _FakeTransport({"/charts/historical": {"open": []}})
    adapter = DhanMarketDataAdapter(transport=transport, wire=_dhan_wire())
    adapter.get_history(
        InstrumentId.parse("NSE:RELIANCE"),
        TimeFrame(value="day"),
        datetime(2024, 3, 9),
        datetime(2024, 3, 10),
    )
    # The payload sent to the transport must use YYYY-MM-DD (Dhan requirement).
    _, _, kwargs = next(c for c in transport.calls if c[1] == "/charts/historical")
    payload = kwargs["json"]
    assert payload["fromDate"] == "2024-03-09"
    assert payload["toDate"] == "2024-03-10"
    assert payload["exchangeSegment"] == "NSE_EQ"
    assert payload["instrument"] == "EQUITY"


# ---------------------------------------------------------------------------
# Dhan depth extension delegation
# ---------------------------------------------------------------------------


class _FakeStreaming:
    def __init__(self) -> None:
        self.calls: list[tuple[InstrumentId, Any]] = []

    def stream_depth(
        self, instrument_id: InstrumentId, on_depth: Any = None
    ) -> MarketDepth | None:
        self.calls.append((instrument_id, on_depth))
        return MarketDepth(
            instrument_id=instrument_id,
            bids=(DepthLevel(price=Price(value=Decimal("1272.0")), quantity=Quantity(value=Decimal("100"))),),
            asks=(),
            timestamp=datetime.now(),
        )


def test_dhan_depth_extension_delegates_to_streaming() -> None:
    fake = _FakeStreaming()
    ext = DhanDepth20Extension(_streaming=fake)
    iid = InstrumentId.parse("NSE:RELIANCE")

    captured: list[MarketDepth] = []
    result = ext.full_depth(iid, on_depth=captured.append)
    assert result is not None
    assert len(result.bids) == 1
    # stream_depth was invoked with the same instrument and a working callback.
    assert fake.calls[0][0] == iid
    cb = fake.calls[0][1]
    assert callable(cb)
    cb(result)  # exercise the callback path
    assert len(captured) == 1
    assert captured[0] is result


def test_dhan_depth_extension_no_streaming_returns_none() -> None:
    ext = DhanDepth20Extension(_streaming=None)
    assert ext.full_depth(InstrumentId.parse("NSE:RELIANCE")) is None


# ---------------------------------------------------------------------------
# Dhan order payload parity (dhanClientId, exchangeSegment, disclosedQuantity)
# ---------------------------------------------------------------------------


def test_dhan_from_place_command_includes_required_fields() -> None:
    wire = DhanWire(client_id="testclient")
    wire.register_security(InstrumentId.parse("NSE:RELIANCE"), "2885")
    command = PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("1250.5")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
        product_type=ProductType.INTRADAY,
        disclosed_quantity=Quantity(value=Decimal("2")),
    )
    body = wire.from_place_command(command)
    assert body["exchangeSegment"] == "NSE_EQ"
    assert body["securityId"] == "2885"
    assert body["disclosedQuantity"] == 2
    assert body["dhanClientId"] == "testclient"


# ---------------------------------------------------------------------------
# Upstox order payload parity (disclosed_quantity, market_protection)
# ---------------------------------------------------------------------------


def test_upstox_from_place_command_includes_required_fields() -> None:
    wire = UpstoxWire()
    wire.register_key(InstrumentId.parse("NSE:RELIANCE"), "NSE_EQ|INE002A01018")
    command = PlaceOrderCommand(
        instrument_id=InstrumentId.parse("NSE:RELIANCE"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Quantity(value=Decimal("10")),
        price=Price(value=Decimal("1250.5")),
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid.uuid4()),
        product_type=ProductType.INTRADAY,
        disclosed_quantity=Quantity(value=Decimal("2")),
    )
    body = wire.from_place_command(command)
    assert body["disclosed_quantity"] == 2
    assert "market_protection" in body

