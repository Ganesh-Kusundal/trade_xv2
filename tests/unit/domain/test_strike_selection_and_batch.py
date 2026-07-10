"""TH-3/TH-4: batch LTP + OptionChain.select_strikes (instrument OOP core)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.entities.options import OptionChain as OptionChainVO
from domain.entities.options import OptionLeg, OptionStrike
from domain.instruments.instrument_id import InstrumentId
from domain.instruments.timeframes import normalize_timeframe
from domain.options.option_chain import OptionChain
from domain.universe import Session


class _Prov:
    name = "test"

    def __init__(self) -> None:
        self.batch_calls = 0

    def get_quote(self, instrument_id):
        from datetime import datetime, timezone

        from domain.candles.historical import InstrumentRef
        from domain.entities.market import QuoteSnapshot
        from domain.provenance import DataProvenance, SourceIdentity

        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying, exchange=instrument_id.exchange
            ),
            ltp=Decimal("100") if instrument_id.underlying == "RELIANCE" else Decimal("25000"),
            event_time=datetime.now(tz=timezone.utc),
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="test"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="q",
            ),
        )

    def get_quotes_batch(self, instrument_ids):
        self.batch_calls += 1
        return [self.get_quote(i) for i in instrument_ids]

    def get_history(self, *a, **k):
        return []

    def get_history_series(self, *a, **k):
        from domain.candles.historical import HistoricalSeries, InstrumentRef

        return HistoricalSeries(
            bars=[],
            coverage=None,
            instrument=InstrumentRef(symbol="X", exchange="NSE"),
            timeframe="1D",
        )

    def get_depth(self, *a, **k):
        return None

    def get_option_chain(self, underlying, *, expiry=None):
        spot = Decimal("25000")
        strikes = []
        for k in range(-3, 4):
            st = spot + Decimal(str(k * 50))
            strikes.append(
                OptionStrike(
                    strike=st,
                    call=OptionLeg(ltp=Decimal("100"), oi=1000),
                    put=OptionLeg(ltp=Decimal("90"), oi=800),
                )
            )
        und = getattr(underlying, "underlying", "NIFTY")
        ex = getattr(underlying, "exchange", "NSE")
        exp = "2026-12-31"
        if expiry is not None:
            exp = expiry.isoformat() if hasattr(expiry, "isoformat") else str(expiry)
        return OptionChainVO(
            underlying=und,
            exchange=ex,
            expiry=exp,
            strikes=tuple(strikes),
            spot=spot,
        )

    def list_option_expiries(self, underlying):
        return ["2026-12-31", "2027-01-07", "2027-01-14"]

    def get_future_chain(self, *a, **k):
        from domain.entities.options import FutureChain

        return FutureChain(underlying="NIFTY", exchange="NFO", contracts=())

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


def test_ltp_many_resolves_instruments_and_batch():
    prov = _Prov()
    session = Session(prov)
    ltps = session.ltp_many(["RELIANCE", "NIFTY"])
    assert ltps["RELIANCE"] == Decimal("100")
    assert ltps["NIFTY"] == Decimal("25000")
    assert prov.batch_calls >= 1
    # resolve still returns instrument OOP
    inst = session.resolve("RELIANCE")
    assert inst.symbol == "RELIANCE"
    assert inst.id == InstrumentId.equity("NSE", "RELIANCE")
    session.close()


def test_select_strikes_atm_returns_options():
    vo = _Prov().get_option_chain(InstrumentId.index("NSE", "NIFTY"))
    chain = OptionChain(vo)
    sel = chain.select_strikes("ATM")
    assert sel.strike == Decimal("25000")
    assert sel.ce is not None and sel.pe is not None
    assert sel.ce_strike == sel.pe_strike == Decimal("25000")
    # still Option instruments
    assert sel.ce.asset_type == "OPTIONS" or "OPTION" in str(type(sel.ce))


def test_select_strikes_otm_steps():
    vo = _Prov().get_option_chain(InstrumentId.index("NSE", "NIFTY"))
    chain = OptionChain(vo)
    sel = chain.select_strikes("OTM", steps=2)
    assert sel.ce_strike == Decimal("25100")  # 25000 + 2*50
    assert sel.pe_strike == Decimal("24900")
    assert sel.ce is not None and sel.pe is not None


def test_select_strikes_itm_steps():
    vo = _Prov().get_option_chain(InstrumentId.index("NSE", "NIFTY"))
    chain = OptionChain(vo)
    sel = chain.select_strikes("ITM", steps=1)
    assert sel.ce_strike == Decimal("24950")
    assert sel.pe_strike == Decimal("25050")


def test_expiry_at_offset():
    vo = _Prov().get_option_chain(InstrumentId.index("NSE", "NIFTY"))
    chain = OptionChain(
        vo,
        available_expiries=["2026-12-31", "2027-01-07", "2027-01-14"],
    )
    assert chain.expiry_at(0) == date(2026, 12, 31)
    assert chain.expiry_at(1) == date(2027, 1, 7)
    assert chain.expiry_at(2) == date(2027, 1, 14)


def test_instrument_option_chain_offset_and_session_helper():
    prov = _Prov()
    session = Session(prov)
    chain = session.option_chain("NIFTY", expiry=0)
    assert chain.expiry  # non-empty
    sel = chain.select_strikes("ATM")
    assert sel.ce is not None
    # DX facade is thin alias
    ce, pe, strike = session.dx.atm_strikes("NIFTY", expiry=0)
    assert strike == sel.strike
    assert ce is not None and pe is not None
    session.close()


def test_normalize_timeframe_tradehull():
    assert normalize_timeframe("DAY") == "1D"
    assert normalize_timeframe("15") == "15m"
    assert normalize_timeframe("60") == "60m"
    assert normalize_timeframe("1m") == "1m"
