"""Tests for the ported legacy instrument-mapping wheels.

These mirror the legacy ``test_generate_alternate_keys`` / resolver collision
behaviour so v2's port cannot drift (zero-parity rule).
"""

from __future__ import annotations

from decimal import Decimal

from domain.symbols import normalize_symbol, normalize_exchange, make_position_key
from domain.value_objects import InstrumentId
from plugins.brokers.common.instruments import InMemoryInstrumentResolver
from plugins.brokers.common.instruments_keys import generate_alternate_keys


# --- domain.symbols (single source of truth) -------------------------------


def test_normalize_symbol_strips_and_uppercases() -> None:
    assert normalize_symbol("  Reliance  ") == "RELIANCE"
    assert normalize_symbol("reliance") == "RELIANCE"


def test_normalize_exchange() -> None:
    assert normalize_exchange("nse") == "NSE"
    assert normalize_exchange("  bse ") == "BSE"


def test_make_position_key() -> None:
    assert make_position_key("Reliance", "nse") == "RELIANCE:NSE"


# --- generate_alternate_keys (shared alias wheel) ---------------------------
# NOTE: 2026-06-25 -> day=25, so spaced forms read "25 JUN", not "26 JUN".


def test_alternate_keys_option_spaced_and_compact() -> None:
    keys = generate_alternate_keys(
        symbol="NIFTY",
        inst_type="OPTION",
        expiry="2026-06-25",
        strike=Decimal("25000"),
        option_type="CE",
        underlying="NIFTY",
        canonical_symbol="NIFTY 50",
    )
    assert "NIFTY 50" in keys
    assert "NIFTY 25 JUN 25000 CE" in keys
    assert "NIFTY25JUN25000CE" in keys
    assert "NIFTY 25 JUN 2026 25000 CE" in keys
    assert "NIFTY 25 JUN 25000 CALL" in keys  # CALL -> CE conversion


def test_alternate_keys_put_and_future() -> None:
    put = generate_alternate_keys(
        symbol="NIFTY",
        inst_type="OPTION",
        expiry="2026-06-25",
        strike=Decimal("25000"),
        option_type="PE",
        underlying="NIFTY",
        canonical_symbol=None,
    )
    assert "NIFTY 25 JUN 25000 PE" in put

    fut = generate_alternate_keys(
        symbol="NIFTY",
        inst_type="FUTURE",
        expiry="2026-06-25",
        strike=None,
        option_type=None,
        underlying="NIFTY",
        canonical_symbol=None,
    )
    assert "NIFTY JUN FUT" in fut
    assert "NIFTY2026JUNFUT" in fut


def test_alternate_keys_dedup_via_seen_set() -> None:
    keys = generate_alternate_keys(
        symbol="NIFTY",
        inst_type="OPTION",
        expiry="2026-06-25",
        strike=Decimal("25000"),
        option_type="CE",
        underlying="NIFTY",
        canonical_symbol="NIFTY 50",
    )
    assert len(keys) == len(set(keys))


# --- InMemoryInstrumentResolver: collision-proofing + search ---------------


def test_resolver_alias_collision_proof() -> None:
    """Register ONE instrument; multiple text forms must resolve to it."""
    r = InMemoryInstrumentResolver()
    iid = InstrumentId.parse("NSE:NIFTY25JUN25000CE")
    r.register(
        iid,
        {"security_id": "61542"},
        symbol="NIFTY",
        exchange="NSE",
        instrument_type="OPTION",
        underlying="NIFTY",
        expiry="2026-06-25",
        strike="25000",
        option_type="CE",
    )
    assert r.resolve_ref(InstrumentId.parse("NSE:NIFTY25JUN25000CE")).require("security_id") == "61542"
    assert r.resolve_ref(InstrumentId.parse("NSE:NIFTY 25 JUN 25000 CE")).require("security_id") == "61542"
    assert r.resolve_ref(InstrumentId.parse("NSE:NIFTY25JUN25000CE")).require("security_id") == "61542"


def test_resolver_equity_vs_option_no_cross_collision() -> None:
    """Same symbol on different exchanges / types must not collide."""
    r = InMemoryInstrumentResolver()
    eq = InstrumentId.parse("NSE:USDINR")
    fut = InstrumentId.parse("CDS:USDINR")
    r.register(eq, {"security_id": "111"}, symbol="USDINR", exchange="NSE", instrument_type="EQUITY")
    r.register(fut, {"security_id": "222"}, symbol="USDINR", exchange="CDS", instrument_type="FUTURE")
    assert r.resolve_ref(eq).require("security_id") == "111"
    assert r.resolve_ref(fut).require("security_id") == "222"


def test_resolver_search_caps_at_limit() -> None:
    r = InMemoryInstrumentResolver()
    for i in range(50):
        iid = InstrumentId.parse(f"NSE:STOCK{i}")
        r.register(iid, {"security_id": str(i)}, symbol=f"STOCK{i}", exchange="NSE")
    results = r.search("STOCK", limit=20)
    assert len(results) == 20
    assert all(res["symbol"].startswith("STOCK") for res in results)


def test_resolver_search_case_insensitive() -> None:
    r = InMemoryInstrumentResolver()
    r.register(
        InstrumentId.parse("NSE:RELIANCE"),
        {"security_id": "1"},
        symbol="RELIANCE",
        exchange="NSE",
    )
    assert len(r.search("reliance")) == 1
    assert len(r.search("REL")) == 1


def test_resolver_load_from_rows_alias_fanout() -> None:
    r = InMemoryInstrumentResolver()
    r.load_from_rows(
        [
            {
                "instrument_id": "NSE:NIFTY25JUN25000CE",
                "wire": {"security_id": "61542"},
                "alias_fields": {
                    "symbol": "NIFTY",
                    "exchange": "NSE",
                    "instrument_type": "OPTION",
                    "underlying": "NIFTY",
                    "expiry": "2026-06-25",
                    "strike": "25000",
                    "option_type": "CE",
                },
            }
        ]
    )
    assert r.resolve_ref(InstrumentId.parse("NSE:NIFTY 25 JUN 25000 CE")).require("security_id") == "61542"
    assert r.is_loaded()
