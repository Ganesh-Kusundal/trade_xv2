"""Unit tests for the Instrument object model (Equity / OptionChain / live data)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.entities.options import OptionChain as OptionChainVO
from domain.entities.options import OptionStrike
from domain.instruments.instrument import Equity
from domain.instruments.instrument_id import InstrumentId
from domain.options.option_chain import OptionChain
from tests.unit.domain._fakes import FakeProvider, make_depth, make_quote


def _new_equity() -> tuple[Equity, FakeProvider]:
    fp = FakeProvider()
    fp.seed_quote("RELIANCE", "NSE", Decimal("2500"))
    fp.seed_depth("RELIANCE", "NSE")
    instr = Equity("RELIANCE", "NSE", data_provider=fp)
    return instr, fp


def test_instrument_identity():
    instr, _ = _new_equity()
    assert instr.symbol == "RELIANCE"
    assert instr.exchange == "NSE"
    assert instr.asset_type == "EQUITY"
    assert isinstance(instr.id, InstrumentId)


def test_refresh_pulls_quote_and_emits():
    instr, _ = _new_equity()
    q = instr.refresh()
    assert q is not None
    assert instr.quote.ltp == Decimal("2500")
    assert instr.ltp == Decimal("2500")
    assert instr.bid == Decimal("2499.5")
    assert instr.ask == Decimal("2500.5")
    assert instr.spread() == Decimal("1")
    assert instr.mid_price() == Decimal("2500")


def test_history_returns_historical_series():
    from domain.candles.historical import HistoricalSeries

    instr, _ = _new_equity()
    series = instr.history(timeframe="5m", days=30)
    assert isinstance(series, HistoricalSeries)
    # Export adapter still available (lazy pandas)
    df = series.to_dataframe()
    assert not df.empty or series.bar_count == 0  # fakes may return empty


def test_depth_returns_market_depth():
    instr, _ = _new_equity()
    depth = instr.depth()
    assert depth is not None
    assert depth.bids and depth.asks


def test_option_chain_returns_rich_object():
    instr, fp = _new_equity()
    strikes = [
        OptionStrike(strike=Decimal("2400")),
        OptionStrike(strike=Decimal("2500")),
        OptionStrike(strike=Decimal("2600")),
    ]
    fp.seed_chain(
        "RELIANCE",
        "NSE",
        OptionChainVO(
            underlying="RELIANCE",
            exchange="NSE",
            expiry="2026-07-31",
            strikes=tuple(strikes),
            spot=Decimal("2500"),
        ),
    )
    chain = instr.option_chain(date(2026, 7, 31))
    assert isinstance(chain, OptionChain)
    assert chain.underlying == "RELIANCE"
    assert chain.spot == Decimal("2500")
    assert chain.atm is not None
    assert chain.atm.strike == Decimal("2500")


def test_subscribe_returns_active_handle_and_fires_callback():
    instr, fp = _new_equity()
    received = []
    sub = instr.subscribe(lambda iid, q: received.append(q))
    assert sub is not None
    assert sub.is_active is True
    fp.fire_tick("RELIANCE", "NSE", make_quote("RELIANCE", "NSE"))
    assert received
    assert instr.is_live is True


def test_unsubscribe_deactivates_handle():
    instr, fp = _new_equity()
    sub = instr.subscribe(lambda iid, q: None)
    instr.unsubscribe()
    assert sub.is_active is False


def test_depth_subscription_updates_state():
    instr, fp = _new_equity()
    received = []
    sub = instr.subscribe(lambda iid, d: received.append(d), depth=True)
    assert sub is not None
    fp.fire_tick("RELIANCE", "NSE", make_depth("RELIANCE"))
    assert received
    assert instr.market_depth is not None
