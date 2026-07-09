"""FutureChain aggregate composes Future instruments."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.entities.options import FutureChain as FutureChainVO
from domain.entities.options import FutureContract
from domain.futures.future_chain import FutureChain
from domain.instruments.instrument_id import InstrumentId
from domain.universe import Session


class _Prov:
    name = "test"

    def get_quote(self, *a, **k):
        return None

    def get_history(self, *a, **k):
        return []

    def get_history_series(self, *a, **k):
        from domain.candles.historical import HistoricalSeries, InstrumentRef

        return HistoricalSeries(
            bars=[], coverage=None, instrument=InstrumentRef(symbol="X", exchange="NFO"), timeframe="1D"
        )

    def get_depth(self, *a, **k):
        return None

    def get_option_chain(self, *a, **k):
        from domain.entities.options import OptionChain

        return OptionChain(underlying="NIFTY", exchange="NFO", expiry="")

    def get_future_chain(self, underlying):
        return FutureChainVO(
            underlying=getattr(underlying, "underlying", "NIFTY"),
            exchange="NFO",
            expiries=("2026-07-30", "2026-08-28"),
            contracts=(
                FutureContract(symbol="NIFTY", expiry="2026-07-30", ltp=Decimal("25000")),
                FutureContract(symbol="NIFTY", expiry="2026-08-28", ltp=Decimal("25100")),
            ),
        )

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


def test_future_chain_all_and_front():
    vo = _Prov().get_future_chain(InstrumentId.index("NSE", "NIFTY"))
    chain = FutureChain(vo)
    all_f = chain.all()
    assert len(all_f) == 2
    assert all_f[0].expiry == date(2026, 7, 30)
    front = chain.front()
    assert front is not None
    assert front.expiry == date(2026, 7, 30)
    assert chain.expiry_at(1) == date(2026, 8, 28)


def test_instrument_future_chain_via_session():
    session = Session(_Prov())
    idx = session.universe.index("NIFTY")
    chain = idx.future_chain()
    assert len(chain) == 2
    f = chain.front()
    assert f is not None
    assert f.symbol == "NIFTY"
    session.close()
