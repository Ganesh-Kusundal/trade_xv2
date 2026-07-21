"""PR-5 AssetKind + ETF/Commodity/Spot/Currency object-model types."""

from __future__ import annotations

from datetime import date

from domain.instruments.asset_kind import AssetKind
from domain.instruments.instrument import ETF, Commodity, Spot
from domain.instruments.instrument_id import (
    InstrumentId,
    allowed_exchanges,
    register_exchange,
    reset_extra_exchanges,
)
from domain.universe import Session


class _Prov:
    name = "t"

    def get_quote(self, *a, **k):
        return None

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

    def get_option_chain(self, *a, **k):
        from domain.entities.options import OptionChain

        return OptionChain(underlying="", exchange="", expiry="")

    def get_future_chain(self, *a, **k):
        from domain.entities.options import FutureChain

        return FutureChain(underlying="", exchange="")

    def subscribe(self, *a, **k):
        return None

    def unsubscribe(self, *a, **k):
        return None


def test_asset_kind_enum():
    assert AssetKind.ETF.value == "ETF"
    assert AssetKind.parse("future") == AssetKind.FUTURES
    assert AssetKind.parse("OPTIONS") == AssetKind.OPTIONS


def test_instrument_id_etf_spot_commodity():
    etf = InstrumentId.etf("NSE", "NIFTYBEES")
    assert etf.is_etf
    assert etf.asset_type == "ETF"
    assert str(etf) == "NSE:NIFTYBEES"

    spot = InstrumentId.spot("NSE", "USDINR")
    assert spot.is_spot

    com = InstrumentId.commodity("MCX", "CRUDEOIL", date(2026, 11, 19))
    assert com.is_commodity
    assert com.is_future
    assert com.right == "FUT"


def test_mcx_future_defaults_commodity_kind():
    iid = InstrumentId.future("MCX", "GOLD", date(2026, 12, 5))
    assert iid.kind == "COMMODITY"


def test_register_exchange():
    # CDS is a core allowed exchange (FX spot); no registration required.
    reset_extra_exchanges()
    assert "CDS" in allowed_exchanges()
    iid = InstrumentId.currency("CDS", "USDINR")
    assert iid.asset_type == "CURRENCY"

    # Dynamic extra-exchange mechanism still works for genuinely new codes.
    register_exchange("NYSE")
    assert "NYSE" in allowed_exchanges()
    InstrumentId.equity("NYSE", "AAPL")
    reset_extra_exchanges()
    assert "NYSE" not in allowed_exchanges()


def test_universe_typed_factories():
    s = Session(_Prov())
    etf = s.universe.etf("NIFTYBEES")
    assert isinstance(etf, ETF)
    assert etf.id.is_etf
    spot = s.universe.spot("USDINR")
    assert isinstance(spot, Spot)
    com = s.universe.commodity("CRUDEOIL", expiry=date(2026, 11, 19))
    assert isinstance(com, Commodity)
    assert com.id.is_commodity
    # get dispatches
    got = s.universe.get(InstrumentId.etf("NSE", "NIFTYBEES"))
    assert isinstance(got, ETF)
    s.close()


def test_equity_and_etf_share_cash_methods():
    s = Session(_Prov())
    eq = s.universe.equity("RELIANCE")
    etf = s.universe.etf("NIFTYBEES")
    assert hasattr(eq, "refresh") and hasattr(etf, "history")
    assert hasattr(etf, "market") and hasattr(etf, "limit")
    assert not hasattr(etf, "buy")
    s.close()
