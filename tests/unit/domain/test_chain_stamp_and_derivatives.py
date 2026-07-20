"""PR-3b OptionChain OMS stamp + PR-4 derivatives math."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from domain.entities.options import OptionChain as OptionChainVO
from domain.entities.options import OptionLeg, OptionStrike
from domain.instruments.derivatives_math import (
    black_scholes_price,
    future_basis,
    implied_volatility,
    moneyness_label,
    option_payoff,
    year_fraction,
)
from domain.instruments.instrument import Future, Option
from domain.instruments.instrument_id import InstrumentId
from domain.orders.intent import OrderIntent
from domain.ports.protocols import OrderResult
from domain.universe import Session


class _FakeOMS:
    def __init__(self) -> None:
        self.places: list[OrderIntent] = []

    def place(self, intent: OrderIntent) -> OrderResult:
        self.places.append(intent)
        o = MagicMock()
        o.order_id = f"OID-{len(self.places)}"
        return OrderResult.ok(o)


class _ChainProv:
    name = "chain"

    def get_quote(self, instrument_id):
        from datetime import datetime, timezone

        from domain.candles.historical import InstrumentRef
        from domain.entities.market import QuoteSnapshot
        from domain.provenance import DataProvenance, SourceIdentity

        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying, exchange=instrument_id.exchange
            ),
            ltp=Decimal("25000"),
            event_time=datetime.now(tz=timezone.utc),
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="chain"),
                fetched_at=datetime.now(tz=timezone.utc),
                request_id="q",
            ),
        )

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
        for k in range(-2, 3):
            st = spot + Decimal(str(k * 100))
            strikes.append(
                OptionStrike(
                    strike=st,
                    call=OptionLeg(
                        ltp=Decimal("100"),
                        oi=1000,
                        iv=Decimal("0.2"),
                        greeks={"delta": 0.5, "gamma": 0.01, "theta": -1, "vega": 2, "rho": 0.1},
                    ),
                    put=OptionLeg(
                        ltp=Decimal("90"),
                        oi=800,
                        iv=Decimal("0.2"),
                        greeks={"delta": -0.5, "gamma": 0.01, "theta": -1, "vega": 2, "rho": 0.1},
                    ),
                )
            )
        und = getattr(underlying, "underlying", "NIFTY")
        ex = getattr(underlying, "exchange", "NSE")
        return OptionChainVO(
            underlying=und,
            exchange=ex,
            expiry="2026-12-31",
            strikes=tuple(strikes),
            spot=spot,
        )

    def get_future_chain(self, underlying):
        from domain.entities.options import FutureChain, FutureContract

        return FutureChain(
            underlying=getattr(underlying, "underlying", "NIFTY"),
            exchange=getattr(underlying, "exchange", "NFO"),
            contracts=(FutureContract(symbol="NIFTY", expiry="2027-01-28", ltp=Decimal("25100")),),
        )

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


def test_chain_atm_buy_stamped_with_oms():
    oms = _FakeOMS()
    session = Session(_ChainProv(), order_service=oms)
    try:
        idx = session.universe.index("NIFTY")
        chain = idx.option_chain()
        atm = chain.atm
        assert atm is not None
        result = atm.buy(1, price=Decimal("100"), correlation_id="chain:atm:1")
        assert result.success
        assert oms.places[-1].correlation_id == "chain:atm:1"
        # chain legs should resolve order service without ambient
        assert atm._resolve_order_service() is oms
    finally:
        session.close()


def test_chain_calls_stamp_oms():
    oms = _FakeOMS()
    session = Session(_ChainProv(), order_service=oms)
    try:
        chain = session.universe.index("NIFTY").option_chain()
        call0 = chain.calls[0]
        call0.buy(1, correlation_id="call:0")
        assert len(oms.places) == 1
    finally:
        session.close()


def test_option_payoff_and_moneyness():
    exp = date.today() + timedelta(days=30)
    opt = Option(
        InstrumentId.option("NFO", "NIFTY", exp, Decimal("25000"), "CE"),
        strike=Decimal("25000"),
        expiry=exp,
        right="CE",
    )
    assert opt.payoff(Decimal("25100")) == Decimal("100")
    assert opt.intrinsic_value(Decimal("24900")) == Decimal("0")
    assert opt.moneyness(Decimal("25000")) == "ATM"
    assert opt.moneyness(Decimal("26000")) == "ITM"
    put = Option(
        InstrumentId.option("NFO", "NIFTY", exp, Decimal("25000"), "PE"),
        strike=Decimal("25000"),
        expiry=exp,
        right="PE",
    )
    assert put.payoff(Decimal("24900")) == Decimal("100")
    assert put.moneyness(Decimal("24000")) == "ITM"


def test_black_scholes_and_iv_roundtrip():
    spot = Decimal("100")
    strike = Decimal("100")
    t = Decimal("0.25")
    rate = Decimal("0.05")
    vol = Decimal("0.2")
    px = black_scholes_price(spot, strike, t, rate, vol, is_call=True)
    assert px is not None and px > 0
    iv = implied_volatility(px, spot, strike, t, rate, is_call=True)
    assert iv is not None
    assert abs(float(iv) - 0.2) < 0.02

    exp = date.today() + timedelta(days=91)
    opt = Option(
        InstrumentId.option("NFO", "NIFTY", exp, strike, "CE"),
        strike=strike,
        expiry=exp,
        right="CE",
        leg=MagicMock(ltp=px, iv=vol),
    )
    bs = opt.black_scholes(spot, rate=rate, vol=vol)
    assert bs is not None
    assert opt.implied_volatility(px, spot=spot, rate=rate) is not None


def test_future_basis():
    assert future_basis(Decimal("100"), Decimal("98")) == Decimal("2")
    assert future_basis(None, Decimal("1")) is None
    exp = date.today() + timedelta(days=30)
    fut = Future("NIFTY", "NFO", expiry=exp, data_provider=_ChainProv())
    # LTP from refresh via provider
    b = fut.basis()
    # F and S both ~25000 from fake → basis ~0
    assert b is not None
    assert abs(b) < Decimal("200")  # both quotes 25000 in fake


def test_year_fraction_and_payoff_helpers():
    t = year_fraction(date.today() + timedelta(days=365))
    assert t is not None
    assert abs(float(t) - 1.0) < 0.01
    assert option_payoff(Decimal("110"), Decimal("100"), is_call=True) == Decimal("10")
    assert moneyness_label(Decimal("100"), Decimal("100"), is_call=True) == "ATM"


def test_future_continuous_empty():
    exp = date.today() + timedelta(days=30)
    fut = Future("NIFTY", "NFO", expiry=exp)
    series = fut.continuous()
    assert series.bar_count == 0
