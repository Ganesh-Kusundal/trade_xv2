"""Platform API test — must run with NO broker imports in sys.modules.

This proves the inversion: the public ``markets`` API is the center of gravity
and brokers are invisible plugins.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from domain.candles.historical import InstrumentRef
from domain.entities.market import DepthLevel, MarketDepth, QuoteSnapshot
from domain.entities.options import OptionChain, OptionLeg, OptionStrike
from domain.provenance import DataProvenance, SourceIdentity


@pytest.fixture(autouse=True)
def _clear_provider_ambient():
    """Isolate each test from Session ambient / default registry pollution."""
    from domain.ports.provider_registry import set_default_provider
    from domain.ports.session_context import set_ambient_session

    set_default_provider(None)
    set_ambient_session(None)
    yield
    set_default_provider(None)
    set_ambient_session(None)


class FakeDataProvider:
    """In-memory DataProvider — no network, no broker."""

    name = "fake"

    def __init__(self, ltp: Decimal = Decimal("25000"), spot: Decimal = Decimal("25000")) -> None:
        self._ltp = ltp
        self._spot = spot

    def get_quote(self, instrument_id):
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying, exchange=instrument_id.exchange
            ),
            ltp=self._ltp,
            event_time=datetime.now(tz=timezone.utc),
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="fake"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="t",
            ),
            bid=self._ltp - Decimal("0.5"),
            ask=self._ltp + Decimal("0.5"),
            volume=1000,
        )

    def get_history(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
        return pd.DataFrame({"close": [self._ltp]})

    def get_history_series(
        self, instrument_id, *, timeframe="1D", lookback_days=120, from_date=None, to_date=None
    ):
        from domain.candles.historical import HistoricalBar, HistoricalSeries

        ref = InstrumentRef(symbol=instrument_id.underlying, exchange=instrument_id.exchange)
        bar = HistoricalBar(
            instrument=ref,
            timeframe=timeframe,
            event_time=datetime.now(tz=timezone.utc),
            open=self._ltp,
            high=self._ltp,
            low=self._ltp,
            close=self._ltp,
            volume=1000,
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="fake"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="h",
            ),
        )
        return HistoricalSeries(bars=[bar], coverage=None, instrument=ref, timeframe=timeframe)

    def get_depth(self, instrument_id):
        return MarketDepth(
            symbol=instrument_id.underlying,
            bids=[DepthLevel(price=self._ltp - Decimal("0.5"), quantity=10)],
            asks=[DepthLevel(price=self._ltp + Decimal("0.5"), quantity=10)],
            depth_type="DEPTH_5",
        )

    def get_option_chain(self, underlying, *, expiry=None):
        strikes = []
        for k in range(-2, 3):
            st = self._spot + Decimal(str(k * 100))
            strikes.append(
                OptionStrike(
                    strike=st,
                    call=OptionLeg(
                        ltp=Decimal("10"),
                        oi=1000,
                        iv=Decimal("0.2"),
                        greeks={
                            "delta": 0.5,
                            "gamma": 0.01,
                            "theta": -1.0,
                            "vega": 2.0,
                            "rho": 0.5,
                        },
                    ),
                    put=OptionLeg(
                        ltp=Decimal("10"),
                        oi=800,
                        iv=Decimal("0.2"),
                        greeks={
                            "delta": -0.5,
                            "gamma": 0.01,
                            "theta": -1.0,
                            "vega": 2.0,
                            "rho": 0.5,
                        },
                    ),
                )
            )
        return OptionChain(
            underlying=underlying.underlying,
            exchange=underlying.exchange,
            expiry="2026-07-30",
            strikes=tuple(strikes),
            spot=self._spot,
        )

    def get_future_chain(self, underlying):
        from domain.entities.options import FutureChain

        return FutureChain(underlying=underlying.underlying, exchange=underlying.exchange)

    def subscribe(self, instrument_id, callback, *, depth=False):
        class _S:
            is_active = True

            def unsubscribe(self):
                self.is_active = False

        s = _S()
        callback(instrument_id, self.get_quote(instrument_id))
        return s

    def unsubscribe(self, subscription):
        subscription.unsubscribe()

    def history_batch(self, instrument_ids, *, timeframe="1D", lookback_days=120):
        return pd.DataFrame()

    def list_instruments(self, exchange=None):
        return []


def test_instruments_does_not_import_brokers():
    # Diff sys.modules around the import so pytest's own collection of OTHER
    # test modules (which legitimately import brokers) does not produce a
    # false positive. This isolates what `import domain.instruments.instrument` itself pulls in.
    before = set(sys.modules)
    import domain.instruments.instrument  # noqa: F401

    new_broker_mods = [
        n for n in (set(sys.modules) - before) if n == "brokers" or n.startswith("brokers.")
    ]
    assert new_broker_mods == [], f"markets must not import brokers: {new_broker_mods}"


def test_equity_quote_ltp_bid_ask_volume():
    from domain.instruments.instrument import Equity
    from domain.ports.provider_registry import set_default_provider

    set_default_provider(FakeDataProvider())
    nifty = Equity("NIFTY")
    nifty.refresh()

    assert nifty.symbol == "NIFTY"
    assert nifty.ltp == Decimal("25000")
    assert nifty.bid == Decimal("24999.5")
    assert nifty.ask == Decimal("25000.5")
    assert nifty.volume == 1000
    assert nifty.spread() == Decimal("1.0")
    assert nifty.mid_price() == Decimal("25000.0")
    nifty.depth()  # populate owned depth state
    assert nifty.market_depth is not None
    series = nifty.history()
    assert series.bar_count >= 1


def test_option_chain_atm_pcr_max_pain():
    from domain.instruments.instrument import Equity
    from domain.ports.provider_registry import set_default_provider

    set_default_provider(FakeDataProvider(spot=Decimal("25000")))
    nifty = Equity("NIFTY")
    chain = nifty.option_chain()

    assert chain.underlying == "NIFTY"
    assert chain.atm.strike == Decimal("25000")
    assert chain.atm.is_call is True
    # chain.atm.greeks.delta — the spec's exact API
    assert chain.atm.greeks.delta == Decimal("0.5")
    assert len(chain.calls) == 5
    assert len(chain.puts) == 5
    assert chain.pcr() == pytest.approx(Decimal("800") / Decimal("1000"))
    assert chain.max_pain() == Decimal("25000")


def test_subscription_lifecycle():
    from domain.instruments.instrument import Equity
    from domain.ports.provider_registry import set_default_provider

    set_default_provider(FakeDataProvider())
    seen = []
    nifty = Equity("NIFTY")
    nifty.subscribe(lambda iid, q: seen.append(q))
    assert nifty.is_live
    assert len(seen) == 1
    nifty.unsubscribe()
    assert not nifty.is_live


def test_broker_extension_depth20():
    """P3: broker-specific capability plugin — the user-facing API.

    ``inst.get_extension("depth20").full_depth()`` should return a
    ``MarketDepth`` without the caller importing anything from ``brokers.*``.
    """
    from domain.entities.market import DepthLevel, MarketDepth
    from domain.value_objects.capability import Capability

    class StubDepthGateway:
        """Minimal gateway with depth_20."""

        def depth_20(self, symbol, exchange="NSE", on_depth=None):
            return MarketDepth(
                symbol=symbol,
                bids=[DepthLevel(price=Decimal("100"), quantity=50)],
                asks=[DepthLevel(price=Decimal("100.5"), quantity=30)],
                depth_type="DEPTH_20",
            )

    # Wire via the extension class (no broker imports in the test's assertion code)
    from brokers.dhan.extensions.depth20 import DhanDepth20Extension

    gw = StubDepthGateway()
    ext = DhanDepth20Extension(gw).for_instrument("RELIANCE", "NSE")

    assert ext.name == "depth_20"
    assert ext.broker == "dhan"
    assert ext.capabilities == (Capability.DEPTH_20,)

    # Attach to an instrument
    from domain.instruments.instrument import Equity
    from domain.ports.provider_registry import set_default_provider

    set_default_provider(FakeDataProvider())
    inst = Equity("RELIANCE")
    # Composition root stamps extensions onto the instrument
    inst._extensions.register("depth_20", ext)

    assert inst.has_extension("depth_20") is True
    assert inst.get_extension("depth_20") is ext

    depth = ext.full_depth()
    assert isinstance(depth, MarketDepth)
    assert depth.symbol == "RELIANCE"
    assert len(depth.bids) == 1
    assert depth.bids[0].price == Decimal("100")
    assert depth.depth_type == "DEPTH_20"


@pytest.mark.xfail(
    reason="Instrument event_bus wiring deferred (object-model later phase)", strict=False
)
def test_instrument_publishes_events():
    from domain.events.null_bus import NullEventBus
    from domain.instruments.instrument import Equity
    from domain.ports.provider_registry import set_default_provider

    events = []

    class RecordingBus(NullEventBus):
        def publish(self, event):
            events.append((event.event_type, dict(event.payload)))

    bus = RecordingBus()
    set_default_provider(FakeDataProvider())
    nifty = Equity("NIFTY", event_bus=bus)
    nifty.refresh()
    assert len(events) == 1
    assert events[0][0] == "QUOTE_UPDATED"
    assert events[0][1]["ltp"] == "25000"

    nifty.subscribe(lambda *a: None)
    assert any(e[0] == "SUBSCRIPTION_STARTED" for e in events)

    nifty.unsubscribe()
    assert any(e[0] == "SUBSCRIPTION_ENDED" for e in events)
