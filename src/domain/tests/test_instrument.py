"""Unit tests for the Instrument object model (Equity / OptionChain / events)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from domain.entities.options import OptionChain as OptionChainVO
from domain.entities.options import OptionStrike
from domain.instruments.instrument import Equity, Option
from domain.instruments.instrument_id import InstrumentId
from domain.options.option_chain import OptionChain
from domain.tests._fakes import FakeEventBus, FakeProvider, make_depth, make_quote


def _new_equity() -> tuple[Equity, FakeProvider, FakeEventBus]:
    bus = FakeEventBus()
    fp = FakeProvider()
    fp.seed_quote("RELIANCE", "NSE", Decimal("2500"))
    fp.seed_depth("RELIANCE", "NSE")
    instr = Equity("RELIANCE", "NSE", provider=fp, event_bus=bus)
    return instr, fp, bus


def test_instrument_identity():
    instr, _, _ = _new_equity()
    assert instr.symbol == "RELIANCE"
    assert instr.exchange == "NSE"
    assert instr.asset_type == "EQUITY"
    assert isinstance(instr.id, InstrumentId)


def test_refresh_pulls_quote_and_emits():
    instr, _, bus = _new_equity()
    q = instr.refresh()
    assert q is not None
    assert instr.quote.ltp == Decimal("2500")
    assert instr.ltp == Decimal("2500")
    assert instr.bid == Decimal("2499.5")
    assert instr.ask == Decimal("2500.5")
    assert instr.spread() == Decimal("1")
    assert instr.mid_price() == Decimal("2500")
    assert bus.count("QUOTE_UPDATED") == 1


def test_history_returns_dataframe():
    instr, _, _ = _new_equity()
    df = instr.history(timeframe="5m", days=30)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "close" in df.columns


def test_depth_returns_market_depth():
    instr, _, _ = _new_equity()
    depth = instr.depth()
    assert depth is not None
    assert depth.bids and depth.asks
    assert instr.market_depth is depth


def test_option_chain_returns_rich_object():
    instr, fp, _ = _new_equity()
    strikes = [
        OptionStrike(strike=Decimal("2400")),
        OptionStrike(strike=Decimal("2500")),
        OptionStrike(strike=Decimal("2600")),
    ]
    fp.seed_chain("RELIANCE", "NSE", OptionChainVO(
        underlying="RELIANCE", exchange="NSE", expiry="2026-07-31", strikes=tuple(strikes),
        spot=Decimal("2500"),
    ))
    chain = instr.option_chain(date(2026, 7, 31))
    assert isinstance(chain, OptionChain)
    assert chain.underlying == "RELIANCE"
    assert chain.spot == Decimal("2500")
    assert chain.atm is not None
    assert chain.atm.strike == Decimal("2500")


def test_subscribe_returns_tracked_subscription_and_emits_started():
    instr, fp, bus = _new_equity()
    received = []
    sub = instr.subscribe(lambda iid, q: received.append(q))
    from domain.instruments.subscription import Subscription

    assert isinstance(sub, Subscription)
    assert bus.count("SUBSCRIPTION_STARTED") == 1
    # simulate a live tick
    fp.fire_tick("RELIANCE", "NSE", make_quote("RELIANCE", "NSE"))
    assert sub.tick_count == 1
    assert bus.count("TICK") == 1
    assert received


def test_unsubscribe_emits_ended_and_deactivates():
    instr, fp, bus = _new_equity()
    sub = instr.subscribe(lambda iid, q: None)
    instr.unsubscribe()
    assert bus.count("SUBSCRIPTION_ENDED") == 1
    assert sub.is_active is False
    assert sub.tick_count == 0


def test_depth_subscription_emits_depth_updated():
    instr, fp, bus = _new_equity()
    sub = instr.subscribe(lambda iid, d: None, depth=True)
    fp.fire_tick("RELIANCE", "NSE", make_depth("RELIANCE"))
    assert sub.depth_count == 1
    assert bus.count("DEPTH_UPDATED") == 1
