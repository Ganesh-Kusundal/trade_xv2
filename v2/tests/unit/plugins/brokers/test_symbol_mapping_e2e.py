"""End-to-end symbol-mapping validation: fixture row → adapter parse → wire
bulk registration → security_id/instrument_key + segment resolution.

Covers the full instrument matrix (equity, future, option, index) for both
brokers, plus the critical regressions from the surgical refactor:

* A derivative ON an index must never resolve to the index's own wire id
  (``NFO:NIFTY:…`` is NOT security_id "13" / key "NSE_INDEX|Nifty 50").
* A pure index resolves from the shared registry even with no master loaded.
* The Dhan strike sentinel (-0.01 on futures) never leaks into the entity.
* ``reverse()`` round-trips a wire id back to the canonical InstrumentId.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from domain.enums import InstrumentType
from domain.value_objects import InstrumentId
from plugins.brokers.dhan.adapters.instruments import DhanInstrumentAdapter
from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.upstox.adapters.instruments import UpstoxInstrumentAdapter
from plugins.brokers.upstox.wire import UpstoxWire

# ── Dhan: real scrip-master column order ─────────────────────────────────────

DHAN_HEADER = (
    "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,"
    "SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,"
    "SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,"
    "SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME"
)

DHAN_E2E_CSV = "\n".join(
    [
        DHAN_HEADER,
        # Equity
        "NSE,E,2885,EQUITY,0,RELIANCE-EQ,1.0,RELIANCE,,,,0.05,,,RELIANCE",
        # Index future — underlying NIFTY, -0.01 strike sentinel
        "NSE,D,44321,FUTIDX,0,NIFTY24JULFUT,50.0,NIFTY FUT,2026-07-30 15:30:00,-0.01000,XX,0.05,M,FUTIDX,,NIFTY",
        # Index option
        "NSE,D,98765,OPTIDX,0,NIFTY24JUL24000CE,50.0,NIFTY 24JUL 24000 CE,2026-07-30 15:30:00,24000.0000,CE,0.05,M,OPTIDX,,NIFTY",
        # Stock option
        "NSE,D,55555,OPTSTK,0,RELIANCE24JUL1500PE,1200.0,RELIANCE 24JUL 1500 PE,2026-07-30 15:30:00,1500.0000,PE,0.05,M,OPTSTK,,RELIANCE",
        # Currency future — -0.01 strike sentinel
        "NSE,C,1026077,FUTCUR,0,USDINR-28AUG2026-FUT,1.0,USDINR AUG FUT,2026-08-28 14:30:00,-0.01000,XX,0.2500,M,FUTCUR,,USDINR",
    ]
)


def _dhan_adapter() -> DhanInstrumentAdapter:
    adapter = DhanInstrumentAdapter(transport=MagicMock())
    adapter._parse_csv_to_instruments(DHAN_E2E_CSV)
    return adapter


class TestDhanEndToEnd:
    def test_equity_resolves(self) -> None:
        adapter = _dhan_adapter()
        iid = InstrumentId.parse("NSE:RELIANCE")
        assert adapter._wire.security_id(iid) == "2885"
        assert adapter._wire.get_segment(iid) == "NSE_EQ"
        assert adapter._by_id[iid.value].instrument_type == InstrumentType.EQUITY

    def test_index_future_resolves_to_own_id_not_index(self) -> None:
        adapter = _dhan_adapter()
        iid = InstrumentId.parse("NFO:NIFTY:20260730:FUT")
        # The future's own security_id — NOT "13" (the NIFTY index).
        assert adapter._wire.security_id(iid) == "44321"
        assert adapter._wire.get_segment(iid) == "NSE_FNO"
        inst = adapter._by_id[iid.value]
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.strike is None  # -0.01 sentinel dropped

    def test_index_option_resolves_to_own_id_not_index(self) -> None:
        adapter = _dhan_adapter()
        iid = InstrumentId.parse("NFO:NIFTY:20260730:24000:CE")
        assert adapter._wire.security_id(iid) == "98765"  # NOT "13"
        assert adapter._wire.get_segment(iid) == "NSE_FNO"
        inst = adapter._by_id[iid.value]
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.strike == Decimal("24000")

    def test_stock_option_resolves(self) -> None:
        adapter = _dhan_adapter()
        iid = InstrumentId.parse("NFO:RELIANCE:20260730:1500:PE")
        assert adapter._wire.security_id(iid) == "55555"
        assert adapter._wire.get_segment(iid) == "NSE_FNO"
        assert adapter._by_id[iid.value].instrument_type == InstrumentType.OPTION

    def test_currency_future_resolves_with_sentinel_dropped(self) -> None:
        adapter = _dhan_adapter()
        iid = InstrumentId.parse("CDS:USDINR:20260828:FUT")
        assert adapter._wire.security_id(iid) == "1026077"
        assert adapter._wire.get_segment(iid) == "NSE_CURRENCY"
        inst = adapter._by_id[iid.value]
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.strike is None  # -0.01 sentinel dropped

    def test_pure_index_from_registry_without_master(self) -> None:
        wire = DhanWire()  # no master loaded at all
        iid = InstrumentId.parse("NSE:NIFTY")
        assert wire.security_id(iid) == "13"
        assert wire.get_segment(iid) == "IDX_I"

    def test_reverse_round_trip(self) -> None:
        adapter = _dhan_adapter()
        resolver = adapter._wire._resolver
        assert resolver.reverse("security_id", "44321") == InstrumentId.parse(
            "NFO:NIFTY:20260730:FUT"
        )
        assert resolver.reverse("security_id", "2885") == InstrumentId.parse("NSE:RELIANCE")
        assert resolver.reverse("security_id", "no-such-id") is None


# ── Upstox: real complete.json.gz row shape ──────────────────────────────────

UPSTOX_E2E_ROWS = [
    {
        "instrument_key": "NSE_EQ|INE002A01018",
        "segment": "NSE_EQ",
        "symbol": "RELIANCE",
        "instrument_type": "EQUITY",
        "lot_size": 1,
        "tick_size": 0.05,
    },
    {
        "instrument_key": "NSE_FO|44321",
        "segment": "NSE_FO",
        "symbol": "NIFTY 30 JUL 2026 FUT",
        "instrument_type": "FUTIDX",
        "underlying_symbol": "NIFTY",
        "expiry": "2026-07-30",
        "lot_size": 50,
        "tick_size": 0.05,
    },
    {
        "instrument_key": "NSE_FO|98765",
        "segment": "NSE_FO",
        "symbol": "NIFTY 30 JUL 2026 24000 CE",
        "instrument_type": "OPTIDX",
        "underlying_symbol": "NIFTY",
        "expiry": "2026-07-30",
        "strike_price": 24000,
        "option_type": "CE",
        "lot_size": 50,
        "tick_size": 0.05,
    },
]


def _upstox_adapter() -> UpstoxInstrumentAdapter:
    adapter = UpstoxInstrumentAdapter(transport=MagicMock())
    adapter._rows_to_instruments([dict(r) for r in UPSTOX_E2E_ROWS])
    return adapter


class TestUpstoxEndToEnd:
    def test_equity_resolves(self) -> None:
        adapter = _upstox_adapter()
        iid = InstrumentId.parse("NSE:RELIANCE")
        assert adapter._wire.instrument_key(iid) == "NSE_EQ|INE002A01018"
        assert adapter._wire.get_segment(iid) == "NSE_EQ"
        assert adapter._by_id[iid.value].instrument_type == InstrumentType.EQUITY

    def test_index_future_classified_future_not_option(self) -> None:
        adapter = _upstox_adapter()
        iid = InstrumentId.parse("NFO:NIFTY:20260730:FUT")
        # Explicit instrument_type field wins over the segment-level guess.
        assert adapter._by_id[iid.value].instrument_type == InstrumentType.FUTURE
        assert adapter._wire.instrument_key(iid) == "NSE_FO|44321"
        assert adapter._wire.get_segment(iid) == "NSE_FO"  # NOT "NSE_INDEX"

    def test_index_option_resolves_to_own_key_not_index(self) -> None:
        adapter = _upstox_adapter()
        iid = InstrumentId.parse("NFO:NIFTY:20260730:24000:CE")
        # The option's own key — NOT "NSE_INDEX|Nifty 50".
        assert adapter._wire.instrument_key(iid) == "NSE_FO|98765"
        assert adapter._wire.get_segment(iid) == "NSE_FO"
        assert adapter._by_id[iid.value].instrument_type == InstrumentType.OPTION

    def test_pure_index_from_registry_without_master(self) -> None:
        wire = UpstoxWire()  # no master loaded at all
        iid = InstrumentId.parse("NSE:NIFTY")
        assert wire.instrument_key(iid) == "NSE_INDEX|Nifty 50"
        assert wire.get_segment(iid) == "NSE_INDEX"

    def test_reverse_round_trip(self) -> None:
        adapter = _upstox_adapter()
        resolver = adapter._wire._resolver
        assert resolver.reverse("instrument_key", "NSE_FO|44321") == InstrumentId.parse(
            "NFO:NIFTY:20260730:FUT"
        )
        assert resolver.reverse("instrument_key", "no-such-key") is None
