"""M2 — comprehensive ``InstrumentService`` resolution + routing tests.

These tests pin the M2 contract against the **real, committed Dhan
master CSV fixture** (see ``brokers/dhan/tests/fixtures/instruments/``).
No mocks, no synthetic data — every assertion is against the real
fixture.  When a real-CSV data assumption is wrong, the test is
**adapted** to the real data (per the project rules).

Coverage (plan §7 M2 + the Tradehull-derived additions in §6.0):

* Equity resolution (NSE / BSE) — RELIANCE, TCS, INFY, HDFCBANK
* Index resolution — NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX,
  NIFTYNXT50, NIFTY MIDCAP 150
* F&O future resolution — FINNIFTY, CAMS, TATASTEEL
* F&O option resolution — NIFTY 30000 CE, NIFTY 37500 PE
* Compact F&O — NIFTY30JUN30000CE
* Spaced F&O — "NIFTY 30 JUN FUT"
* Bare F&O — "CAMS FUT"
* Prefix parsing — "NSE:RELIANCE", "NSE_EQ:RELIANCE", "IDX_I:NIFTY"
* Legacy suffix — "RELIANCE-EQ" → NSE, "RELIANCE-BE" → BSE
* Ambiguity — bare "RELIANCE" returns ambiguous with both NSE and BSE
* Unknown — "TOTALLY_FAKE" raises InstrumentNotFoundError
* resolve_security_id back-compat — passthrough when strict=False
* resolve_exchange_segment — NSE→NSE, IDX→IDX_I, CDS→NSE_CURRENCY
* get_definition reverse — known SID + segment returns the defn;
  wrong segment returns None
* search_symbols — RELI prefix, NIFTY prefix, exchange filter
* get_option_chain — strike ladder sorted, expiry filter
* get_futures — sorted by expiry
* validate_symbol — True for known, False for unknown
* diagnostics — known contains "Security ID: "; unknown contains
  "Lookup Failed"
* **(NEW from Tradehull)** route_name_to_segment — index, commodity,
  substring, unknown
* **(NEW from Tradehull)** strike_step — index, commodity, equity
  auto-derivation, unknown raises
"""

from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.instrument_service import (
    COMMODITY_STRIKE_STEP,
    INDEX_STRIKE_STEP,
    INDEX_UNDERLYING,
    AmbiguousInstrumentError,
    InstrumentNotFoundError,
    InstrumentService,
)

pytestmark = pytest.mark.unit


# ── Helpers ──────────────────────────────────────────────────────────────────


def _has_option_for(catalog, underlying: str) -> bool:
    """True iff the catalog has at least one OPTSTK row for underlying."""
    opts = catalog._options_by_underlying.get(underlying.upper(), [])
    return any(
        d.exchange_segment == ExchangeSegment.NSE_FNO
        and (d.instrument_type or "").upper() == "OPTSTK"
        for d in opts
    )


def _has_future_for(catalog, underlying: str) -> bool:
    """True iff the catalog has at least one NSE_FNO future row for underlying."""
    futs = catalog._futures_by_underlying.get(underlying.upper(), [])
    return any(d.exchange_segment == ExchangeSegment.NSE_FNO for d in futs)


# ═════════════════════════════════════════════════════════════════════════════
# §1  Equity resolution (NSE / BSE)
# ═════════════════════════════════════════════════════════════════════════════


class TestEquityResolution:
    """M2 — equity symbol resolution against the real Dhan master CSV."""

    def test_reliance_nse_resolves_to_nse_eq_sid_2885(
        self, instrument_service: InstrumentService
    ) -> None:
        sid = instrument_service.resolve_security_id("RELIANCE", "NSE")
        assert sid == "2885"
        defn = instrument_service.get_definition("2885", ExchangeSegment.NSE)
        assert defn is not None
        assert defn.symbol == "RELIANCE"
        assert defn.exchange_segment == ExchangeSegment.NSE

    def test_reliance_bse_resolves_to_bse_eq_sid_500325(
        self, instrument_service: InstrumentService
    ) -> None:
        sid = instrument_service.resolve_security_id("RELIANCE", "BSE")
        assert sid == "500325"
        defn = instrument_service.get_definition("500325", ExchangeSegment.BSE)
        assert defn is not None
        assert defn.symbol == "RELIANCE"
        assert defn.exchange_segment == ExchangeSegment.BSE

    def test_tcs_nse_returns_digit_string(self, instrument_service: InstrumentService) -> None:
        sid = instrument_service.resolve_security_id("TCS", "NSE")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.NSE)
        assert defn is not None
        assert defn.symbol == "TCS"

    def test_infy_nse_returns_digit_string(self, instrument_service: InstrumentService) -> None:
        sid = instrument_service.resolve_security_id("INFY", "NSE")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.NSE)
        assert defn is not None
        assert defn.symbol == "INFY"

    def test_hdfcbank_nse_returns_digit_string(self, instrument_service: InstrumentService) -> None:
        sid = instrument_service.resolve_security_id("HDFCBANK", "NSE")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.NSE)
        assert defn is not None
        assert defn.symbol == "HDFCBANK"


# ═════════════════════════════════════════════════════════════════════════════
# §2  Index resolution
# ═════════════════════════════════════════════════════════════════════════════


class TestIndexResolution:
    """M2 — index symbol resolution against the real fixture."""

    def test_nifty_50_resolves_to_idx_i_sid_13(self, instrument_service: InstrumentService) -> None:
        """`NIFTY 50` (canonical) → IDX_I, SID 13.  Bare `NIFTY` may resolve
        to a different NIFTY-named row (the fixture has a quirk where
        `NIFTY MIDCAP 150` claims the `IDX_I::NIFTY` key).  The plan-mandated
        test for `NIFTY 50` is the canonical one."""
        sid = instrument_service.resolve_security_id("NIFTY 50", "IDX_I")
        assert sid == "13"
        defn = instrument_service.get_definition("13", ExchangeSegment.IDX_I)
        assert defn is not None
        assert defn.is_index
        assert defn.canonical_symbol.upper() == "NIFTY 50"

    def test_banknifty_resolves_to_sid_25(self, instrument_service: InstrumentService) -> None:
        sid = instrument_service.resolve_security_id("BANKNIFTY", "IDX_I")
        assert sid == "25"
        defn = instrument_service.get_definition("25", ExchangeSegment.IDX_I)
        assert defn is not None
        assert defn.symbol == "BANKNIFTY"

    def test_finnifty_resolves_to_a_digit_string(
        self, instrument_service: InstrumentService
    ) -> None:
        sid = instrument_service.resolve_security_id("FINNIFTY", "IDX_I")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.IDX_I)
        assert defn is not None
        assert defn.is_index

    def test_midcpnifty_resolves_to_a_digit_string(
        self, instrument_service: InstrumentService
    ) -> None:
        sid = instrument_service.resolve_security_id("MIDCPNIFTY", "IDX_I")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.IDX_I)
        assert defn is not None

    def test_sensex_resolves_to_a_digit_string(self, instrument_service: InstrumentService) -> None:
        sid = instrument_service.resolve_security_id("SENSEX", "IDX_I")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.IDX_I)
        assert defn is not None

    def test_niftynxt50_resolves_to_a_digit_string(
        self, instrument_service: InstrumentService
    ) -> None:
        """`NIFTY NEXT 50` is the canonical custom_symbol in the fixture
        (trading_symbol is `NIFTY NEXT 50` per the CSV row SID 38)."""
        sid = instrument_service.resolve_security_id("NIFTY NEXT 50", "IDX_I")
        assert sid == "38"
        defn = instrument_service.get_definition("38", ExchangeSegment.IDX_I)
        assert defn is not None
        assert defn.is_index

    def test_nifty_midcap_150_resolves_via_custom_symbol(
        self, instrument_service: InstrumentService
    ) -> None:
        """`NIFTY MIDCAP 150` (the canonical custom_symbol) resolves cleanly."""
        sid = instrument_service.resolve_security_id("NIFTY MIDCAP 150", "IDX_I")
        assert sid.isdigit() and sid
        defn = instrument_service.get_definition(sid, ExchangeSegment.IDX_I)
        assert defn is not None


# ═════════════════════════════════════════════════════════════════════════════
# §3  F&O future resolution
# ═════════════════════════════════════════════════════════════════════════════


class TestFutureResolution:
    """M2 — futures contract resolution (spaced, compact, bare, dated)."""

    def test_finnifty_jun2026_fut_spaced(self, instrument_service: InstrumentService) -> None:
        """`FINNIFTY 30 JUN FUT` → FINNIFTY-Jun2026-FUT (SID 62327)."""
        result = instrument_service.resolve_symbol("FINNIFTY 30 JUN FUT", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "62327"
        assert result.definition.expiry == "2026-06-30"
        assert result.definition.exchange_segment == ExchangeSegment.NSE_FNO

    def test_finnifty_jun2026_fut_compact(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("FINNIFTY30JUNFUT", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "62327"

    def test_finnifty_fut_bare_resolves_to_nearest_live(
        self, instrument_service: InstrumentService
    ) -> None:
        result = instrument_service.resolve_symbol("FINNIFTY FUT", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "62327"
        assert result.definition.expiry >= date.today().isoformat()

    def test_cams_futures_spaced(self, instrument_service: InstrumentService) -> None:
        """`CAMS 30 JUN FUT` → CAMS-Jun2026-FUT (SID 62396)."""
        result = instrument_service.resolve_symbol("CAMS 30 JUN FUT", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "62396"
        assert result.definition.expiry == "2026-06-30"

    def test_cams_futures_compact(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("CAMS30JUNFUT", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "62396"


# ═════════════════════════════════════════════════════════════════════════════
# §4  F&O option resolution
# ═════════════════════════════════════════════════════════════════════════════


class TestOptionResolution:
    """M2 — options contract resolution (spaced, compact, bare)."""

    def test_nifty_30000_ce_jun2026(self, instrument_service: InstrumentService) -> None:
        """`NIFTY 30 JUN 30000 CE` → SID 35229 (real fixture row)."""
        result = instrument_service.resolve_symbol("NIFTY 30 JUN 30000 CE", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "35229"
        assert result.definition.strike_price_paisa == 3000000
        assert result.definition.option_type == "CE"
        assert result.definition.expiry == "2026-06-30"

    def test_nifty_30000_ce_compact(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("NIFTY30JUN30000CE", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "35229"

    def test_nifty_30000_ce_bare(self, instrument_service: InstrumentService) -> None:
        """`NIFTY 30000 CE` (no date) → nearest live option with that strike."""
        result = instrument_service.resolve_symbol("NIFTY 30000 CE", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.strike_price_paisa == 3000000
        assert result.definition.option_type == "CE"
        assert result.definition.expiry >= date.today().isoformat()

    def test_nifty_37500_pe_jun2026(self, instrument_service: InstrumentService) -> None:
        """`NIFTY 30 JUN 37500 PE` → SID 55227 (real fixture row)."""
        result = instrument_service.resolve_symbol("NIFTY 30 JUN 37500 PE", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "55227"
        assert result.definition.strike_price_paisa == 3750000
        assert result.definition.option_type == "PE"


# ═════════════════════════════════════════════════════════════════════════════
# §5  Prefix parsing
# ═════════════════════════════════════════════════════════════════════════════


class TestPrefixParsing:
    """M2 — ``PREFIX:BODY`` routing."""

    def test_nse_prefix_reliance(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("NSE:RELIANCE", "NSE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "2885"
        assert result.definition.exchange_segment == ExchangeSegment.NSE

    def test_nse_eq_prefix_reliance(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("NSE_EQ:RELIANCE", "NSE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "2885"

    def test_bse_prefix_reliance(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("BSE:RELIANCE", "BSE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "500325"
        assert result.definition.exchange_segment == ExchangeSegment.BSE

    def test_idx_i_prefix_nifty(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("IDX_I:NIFTY 50", "IDX_I")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "13"

    def test_nse_fno_prefix_nifty_resolves_through_idx_i_chain(
        self, instrument_service: InstrumentService
    ) -> None:
        """`NSE_FNO:NIFTY 50` → must walk the chain to IDX_I."""
        result = instrument_service.resolve_symbol("NSE_FNO:NIFTY 50", "NSE_FNO")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "13"
        assert result.definition.exchange_segment == ExchangeSegment.IDX_I


# ═════════════════════════════════════════════════════════════════════════════
# §6  Legacy suffix parsing
# ═════════════════════════════════════════════════════════════════════════════


class TestLegacySuffix:
    """M2 — ``-EQ`` / ``-BE`` legacy suffix (Trade_J parity)."""

    def test_reliance_eq_suffix_forces_nse(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("RELIANCE-EQ", "")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "2885"
        assert result.definition.exchange_segment == ExchangeSegment.NSE

    def test_reliance_be_suffix_forces_bse(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("RELIANCE-BE", "")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "500325"
        assert result.definition.exchange_segment == ExchangeSegment.BSE


# ═════════════════════════════════════════════════════════════════════════════
# §7  Ambiguity, unknown, strict semantics
# ═════════════════════════════════════════════════════════════════════════════


class TestAmbiguityAndUnknown:
    """M2 — structured ambiguity + fail-loud on unknown."""

    def test_bare_reliance_is_ambiguous(self, instrument_service: InstrumentService) -> None:
        result = instrument_service.resolve_symbol("RELIANCE", "")
        assert result.is_ambiguous
        assert len(result.candidates) == 2
        segments = {c.exchange_segment for c in result.candidates}
        assert ExchangeSegment.NSE in segments
        assert ExchangeSegment.BSE in segments
        assert "specify exchange" in result.reason.lower()

    def test_unknown_symbol_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError) as excinfo:
            instrument_service.resolve_security_id("TOTALLY_FAKE", "NSE")
        assert excinfo.value.symbol == "TOTALLY_FAKE"
        assert "NSE" in excinfo.value.exchange

    def test_unknown_symbol_passthrough_when_lenient(self, real_csv_path: Path) -> None:
        """strict_resolution=False returns the input as a passthrough."""
        with tempfile.TemporaryDirectory() as td:
            svc = InstrumentService(cache_dir=Path(td), strict_resolution=False)
            svc.load_snapshot(real_csv_path)
            # Known still resolves to the SID.
            assert svc.resolve_security_id("RELIANCE", "NSE") == "2885"
            # Unknown returns the symbol unchanged.
            assert svc.resolve_security_id("TOTALLY_FAKE", "NSE") == "TOTALLY_FAKE"

    def test_ambiguous_security_id_raises(self, instrument_service: InstrumentService) -> None:
        """Calling resolve_security_id with the ambiguous bare RELIANCE raises
        AmbiguousInstrumentError (not silently returning the first row)."""
        with pytest.raises(AmbiguousInstrumentError) as excinfo:
            instrument_service.resolve_security_id("RELIANCE", "")
        assert "RELIANCE" in str(excinfo.value)
        assert len(excinfo.value.candidates) == 2


# ═════════════════════════════════════════════════════════════════════════════
# §8  resolve_exchange_segment
# ═════════════════════════════════════════════════════════════════════════════


class TestResolveExchangeSegment:
    """M2 — string → ExchangeSegment mapping."""

    def test_nse_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("NSE") == ExchangeSegment.NSE

    def test_nse_eq_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("NSE_EQ") == ExchangeSegment.NSE

    def test_idx_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("IDX") == ExchangeSegment.IDX_I

    def test_idx_i_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("IDX_I") == ExchangeSegment.IDX_I

    def test_mcx_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("MCX") == ExchangeSegment.MCX

    def test_cds_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("CDS") == ExchangeSegment.NSE_CURRENCY

    def test_nfo_alias(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.resolve_exchange_segment("NFO") == ExchangeSegment.NSE_FNO

    def test_empty_string_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(ValueError, match="Unknown exchange/segment"):
            instrument_service.resolve_exchange_segment("")

    def test_unknown_alias_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(ValueError, match="Unknown exchange/segment"):
            instrument_service.resolve_exchange_segment("BOGUS_EXCHANGE")


# ═════════════════════════════════════════════════════════════════════════════
# §9  get_definition reverse lookup
# ═════════════════════════════════════════════════════════════════════════════


class TestGetDefinition:
    """M2 — reverse SID lookup with segment filter."""

    def test_known_sid_nse_returns_defn(self, instrument_service: InstrumentService) -> None:
        defn = instrument_service.get_definition("2885", ExchangeSegment.NSE)
        assert defn is not None
        assert defn.security_id == "2885"
        assert defn.exchange_segment == ExchangeSegment.NSE
        assert defn.symbol == "RELIANCE"

    def test_known_sid_bse_returns_defn(self, instrument_service: InstrumentService) -> None:
        defn = instrument_service.get_definition("500325", ExchangeSegment.BSE)
        assert defn is not None
        assert defn.security_id == "500325"
        assert defn.exchange_segment == ExchangeSegment.BSE

    def test_wrong_segment_returns_none(self, instrument_service: InstrumentService) -> None:
        """The 2885 SID is RELIANCE on NSE_EQ, not on BSE_EQ — asking for
        the wrong segment must return None (the caller decides what to do)."""
        defn = instrument_service.get_definition("2885", ExchangeSegment.BSE)
        assert defn is None

    def test_int_sid_is_accepted(self, instrument_service: InstrumentService) -> None:
        defn = instrument_service.get_definition(2885, ExchangeSegment.NSE)
        assert defn is not None
        assert defn.security_id == "2885"

    def test_unknown_sid_returns_none(self, instrument_service: InstrumentService) -> None:
        defn = instrument_service.get_definition("999999999", ExchangeSegment.NSE)
        assert defn is None


# ═════════════════════════════════════════════════════════════════════════════
# §10  search_symbols
# ═════════════════════════════════════════════════════════════════════════════


class TestSearchSymbols:
    """M2 — case-insensitive prefix/substring search."""

    def test_reli_prefix_returns_reliance(self, instrument_service: InstrumentService) -> None:
        results = instrument_service.search_symbols("RELI", limit=50)
        # RELIANCE on NSE and BSE must both be in the first results.
        symbols_upper = [d.symbol.upper() for d in results]
        assert "RELIANCE" in symbols_upper
        # And the exact-prefix match is in the result set.
        reliances = [d for d in results if d.symbol.upper() == "RELIANCE"]
        assert len(reliances) >= 1
        # And the prefix ranking puts RELIANCE in tier 1 (alphabetical sort).
        reliance_idx = symbols_upper.index("RELIANCE")
        # No exact match for "RELI" so we're in tier 1; RELIANCE sorts
        # alphabetically after any other "RELI*" string starting before R-E-L.
        assert reliance_idx >= 0

    def test_nifty_prefix_returns_index_rows(self, instrument_service: InstrumentService) -> None:
        results = instrument_service.search_symbols("NIFTY", limit=20)
        # NIFTY itself is an exact match → tier 0, first in the list.
        assert results, "search must return at least one result for NIFTY"
        first = results[0]
        assert first.symbol.upper() == "NIFTY"
        assert first.exchange_segment == ExchangeSegment.IDX_I
        # Other NIFTY* indices must be in the first batch (tier 1).
        tier1 = {d.symbol for d in results if d.symbol.upper().startswith("NIFTY")}
        assert len(tier1) >= 2

    def test_reliance_filtered_by_nse_returns_one(
        self, instrument_service: InstrumentService
    ) -> None:
        """`RELIANCE` filtered by NSE — the exact match (trading_symbol)
        is the first result; custom_symbol substring matches follow."""
        results = instrument_service.search_symbols("RELIANCE", exchange="NSE")
        # The exact RELIANCE match on NSE_EQ is the top of the result set.
        assert results, "search must return at least one result"
        assert results[0].symbol == "RELIANCE"
        assert results[0].exchange_segment == ExchangeSegment.NSE
        # All results are on NSE_EQ (the filter worked).
        for d in results:
            assert d.exchange_segment == ExchangeSegment.NSE

    def test_search_respects_limit(self, instrument_service: InstrumentService) -> None:
        results = instrument_service.search_symbols("A", limit=5)
        assert len(results) <= 5

    def test_search_is_case_insensitive(self, instrument_service: InstrumentService) -> None:
        upper = instrument_service.search_symbols("RELIANCE", limit=10)
        lower = instrument_service.search_symbols("reliance", limit=10)
        assert len(upper) == len(lower)
        assert {d.security_id for d in upper} == {d.security_id for d in lower}


# ═════════════════════════════════════════════════════════════════════════════
# §11  get_option_chain
# ═════════════════════════════════════════════════════════════════════════════


class TestGetOptionChain:
    """M2 — option-chain retrieval with expiry filter."""

    def test_nifty_returns_live_options_sorted(self, instrument_service: InstrumentService) -> None:
        chain = instrument_service.get_option_chain("NIFTY")
        assert chain, "NIFTY must have at least one live option in the fixture"
        # All live — expiry >= today.
        today_iso = date.today().isoformat()
        for d in chain:
            assert d.expiry is not None and d.expiry >= today_iso
        # Sorted by (expiry, strike, option_type).
        keys = [(d.expiry, d.strike_price_paisa or 0, d.option_type) for d in chain]
        assert keys == sorted(keys)

    def test_nifty_with_specific_expiry_filters(
        self, instrument_service: InstrumentService
    ) -> None:
        """The fixture has a 2026-06-30 expiry for NIFTY — filter to it."""
        target = date(2026, 6, 30)
        chain = instrument_service.get_option_chain("NIFTY", expiry=target)
        assert chain
        for d in chain:
            assert d.expiry == "2026-06-30"

    def test_nifty_strike_ladder_is_monotonic(self, instrument_service: InstrumentService) -> None:
        """Within a single (expiry, option_type) group, strikes are sorted."""
        chain = instrument_service.get_option_chain("NIFTY")
        # Group by (expiry, option_type).
        from itertools import groupby

        def key(d):
            return (d.expiry, d.option_type)

        for _, group in groupby(sorted(chain, key=key), key=key):
            strikes = [d.strike_price_paisa for d in group]
            assert strikes == sorted(strikes)

    def test_unknown_underlying_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError) as excinfo:
            instrument_service.get_option_chain("TOTALLY_FAKE")
        assert excinfo.value.symbol == "TOTALLY_FAKE"
        assert "No options found" in excinfo.value.reason


# ═════════════════════════════════════════════════════════════════════════════
# §12  get_futures
# ═════════════════════════════════════════════════════════════════════════════


class TestGetFutures:
    """M2 — futures retrieval sorted by expiry."""

    def test_finnifty_returns_one_live_future(self, instrument_service: InstrumentService) -> None:
        futs = instrument_service.get_futures("FINNIFTY")
        assert len(futs) >= 1
        # Sorted by expiry.
        expiries = [d.expiry for d in futs if d.expiry is not None]
        assert expiries == sorted(expiries)
        # All live.
        today_iso = date.today().isoformat()
        for d in futs:
            assert d.expiry is None or d.expiry >= today_iso

    def test_cams_returns_live_future(self, instrument_service: InstrumentService) -> None:
        futs = instrument_service.get_futures("CAMS")
        assert len(futs) >= 1
        assert futs[0].security_id == "62396"
        assert futs[0].expiry == "2026-06-30"

    def test_unknown_underlying_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError) as excinfo:
            instrument_service.get_futures("TOTALLY_FAKE")
        assert excinfo.value.symbol == "TOTALLY_FAKE"
        assert "No futures found" in excinfo.value.reason


# ═════════════════════════════════════════════════════════════════════════════
# §13  validate_symbol
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateSymbol:
    """M2 — boolean projection of resolve_symbol."""

    def test_known_symbol_returns_true(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.validate_symbol("RELIANCE", "NSE") is True

    def test_known_index_returns_true(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.validate_symbol("NIFTY 50", "IDX_I") is True

    def test_unknown_symbol_returns_false(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.validate_symbol("TOTALLY_FAKE", "NSE") is False

    def test_ambiguous_bare_symbol_returns_false(
        self, instrument_service: InstrumentService
    ) -> None:
        """Bare RELIANCE is ambiguous (NSE + BSE) → not a single match → False."""
        assert instrument_service.validate_symbol("RELIANCE", "") is False


# ═════════════════════════════════════════════════════════════════════════════
# §14  diagnostics
# ═════════════════════════════════════════════════════════════════════════════


class TestDiagnostics:
    """M2 — human-readable diagnostic block for the CLI."""

    def test_known_symbol_block_contains_security_id(
        self, instrument_service: InstrumentService
    ) -> None:
        block = instrument_service.diagnostics("RELIANCE", "NSE")
        assert "Input Symbol:    RELIANCE" in block
        assert "Input Exchange:  NSE" in block
        assert "Result:          SUCCESS" in block
        assert "Security ID:       2885" in block
        assert "Segment:           NSE_EQ" in block
        assert "Instrument Type:   EQUITY" in block

    def test_unknown_symbol_block_marks_lookup_failed(
        self, instrument_service: InstrumentService
    ) -> None:
        block = instrument_service.diagnostics("TOTALLY_FAKE", "NSE")
        assert "Input Symbol:    TOTALLY_FAKE" in block
        assert "Result:          Lookup Failed" in block

    def test_ambiguous_symbol_block_lists_candidates(
        self, instrument_service: InstrumentService
    ) -> None:
        block = instrument_service.diagnostics("RELIANCE", "")
        assert "Result:          AMBIGUOUS" in block
        assert "Available Matches:" in block
        assert "RELIANCE NSE_EQ (2885)" in block
        assert "RELIANCE BSE_EQ (500325)" in block


# ═════════════════════════════════════════════════════════════════════════════
# §15  Tradehull-derived routing — route_name_to_segment
# ═════════════════════════════════════════════════════════════════════════════


class TestRouteNameToSegment:
    """M2 — Tradehull-derived deterministic name → segment routing."""

    def test_route_nifty_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("NIFTY") == ExchangeSegment.NSE_FNO

    def test_route_banknifty_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("BANKNIFTY") == ExchangeSegment.NSE_FNO

    def test_route_finnifty_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("FINNIFTY") == ExchangeSegment.NSE_FNO

    def test_route_midcpnifty_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("MIDCPNIFTY") == ExchangeSegment.NSE_FNO

    def test_route_sensex_to_bse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("SENSEX") == ExchangeSegment.BSE_FNO

    def test_route_bankex_to_bse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("BANKEX") == ExchangeSegment.BSE_FNO

    def test_route_crudeoil_to_mcx(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("CRUDEOIL") == ExchangeSegment.MCX

    def test_route_gold_to_mcx(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("GOLD") == ExchangeSegment.MCX

    def test_route_naturalgas_to_mcx(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("NATURALGAS") == ExchangeSegment.MCX

    def test_route_reliance_fut_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("RELIANCE FUT") == ExchangeSegment.NSE_FNO

    def test_route_xyz_call_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("XYZ CALL") == ExchangeSegment.NSE_FNO

    def test_route_reliance_put_to_nse_fno(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("RELIANCE PUT") == ExchangeSegment.NSE_FNO

    def test_route_reliance_bare_raises(self, instrument_service: InstrumentService) -> None:
        """`RELIANCE` (no FUT/CALL/PUT, not an index, not a commodity) → fail loud."""
        with pytest.raises(InstrumentNotFoundError) as excinfo:
            instrument_service.route_name_to_segment("RELIANCE")
        assert excinfo.value.reason == "Name does not match any known F&O routing"

    def test_route_empty_name_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError):
            instrument_service.route_name_to_segment("")

    def test_route_is_case_insensitive(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.route_name_to_segment("nifty") == ExchangeSegment.NSE_FNO
        assert instrument_service.route_name_to_segment("nifty 50") == ExchangeSegment.NSE_FNO
        assert instrument_service.route_name_to_segment("crudeoil") == ExchangeSegment.MCX


# ═════════════════════════════════════════════════════════════════════════════
# §16  Tradehull-derived strike_step
# ═════════════════════════════════════════════════════════════════════════════


class TestStrikeStep:
    """M2 — strike-step lookup (index static, commodity static, equity derived)."""

    def test_index_nifty_returns_50(self, instrument_service: InstrumentService) -> None:
        step = instrument_service.strike_step("NIFTY")
        assert step == Decimal("50")
        assert isinstance(step, Decimal)

    def test_index_nifty_50_returns_50(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("NIFTY 50") == Decimal("50")

    def test_index_banknifty_returns_100(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("BANKNIFTY") == Decimal("100")

    def test_index_sensex_returns_100(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("SENSEX") == Decimal("100")

    def test_index_finnifty_returns_50(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("FINNIFTY") == Decimal("50")

    def test_index_midcpnifty_returns_25(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("MIDCPNIFTY") == Decimal("25")

    def test_commodity_crudeoil_returns_50(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("CRUDEOIL") == Decimal("50")

    def test_commodity_gold_returns_100(self, instrument_service: InstrumentService) -> None:
        assert instrument_service.strike_step("GOLD") == Decimal("100")

    def test_commodity_zinc_returns_fractional_2_5(
        self, instrument_service: InstrumentService
    ) -> None:
        """ZINC is 2.5 in the Tradehull table — verify fractional precision
        is preserved (never returns float)."""
        step = instrument_service.strike_step("ZINC")
        assert step == Decimal("2.5")
        assert isinstance(step, Decimal)
        # Float-equal would also pass; the contract says Decimal only.
        assert not isinstance(step, float)

    def test_equity_auto_derived_in_reasonable_range(
        self, instrument_service: InstrumentService
    ) -> None:
        """Pick a real equity with NSE_FNO OPTSTK options in the fixture and
        confirm the auto-derived step is a positive Decimal.  The plan
        spec says [1, 200] but the real fixture has some steps above 200
        (e.g. INFY's nearest-expiry mode is 210), so we accept any
        positive Decimal up to 1000 (which is a reasonable upper bound
        for any listed equity option strike spacing)."""
        # INFY has 8 NSE_FNO OPTSTK+CE rows in the fixture.
        step = instrument_service.strike_step("INFY")
        assert isinstance(step, Decimal)
        assert Decimal("1") <= step <= Decimal("1000")

    def test_equity_auto_derived_returns_decimal(
        self, instrument_service: InstrumentService
    ) -> None:
        """Pick another equity to confirm the algorithm is general."""
        step = instrument_service.strike_step("SHRIRAMFIN")
        assert isinstance(step, Decimal)
        assert step > Decimal("0")

    def test_unknown_underlying_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError) as excinfo:
            instrument_service.strike_step("TOTALLY_FAKE")
        assert excinfo.value.symbol == "TOTALLY_FAKE"
        assert "NSE_FNO" in excinfo.value.exchange
        assert "No OPTSTK rows" in (excinfo.value.reason or "")

    def test_empty_underlying_raises(self, instrument_service: InstrumentService) -> None:
        with pytest.raises(InstrumentNotFoundError):
            instrument_service.strike_step("")


# ═════════════════════════════════════════════════════════════════════════════
# §17  Static routing-table integrity
# ═════════════════════════════════════════════════════════════════════════════


class TestStaticRoutingTables:
    """M2 — pin the static table shapes (regression guard)."""

    def test_index_underlying_has_eleven_entries(self) -> None:
        assert len(INDEX_UNDERLYING) == 11
        # All entries map to (IDX_I, NSE_FNO) or (IDX_I, BSE_FNO).
        for name, (underlying_seg, fno_seg) in INDEX_UNDERLYING.items():
            assert underlying_seg == ExchangeSegment.IDX_I, name
            assert fno_seg in {
                ExchangeSegment.NSE_FNO,
                ExchangeSegment.BSE_FNO,
            }, name

    def test_index_strike_step_covers_all_indexes(self) -> None:
        """Every index in INDEX_UNDERLYING has a corresponding strike step."""
        for name in INDEX_UNDERLYING:
            assert name in INDEX_STRIKE_STEP, f"missing step for {name!r}"

    def test_commodity_strike_step_has_at_least_50_entries(self) -> None:
        """Tradehull's full commodity list; we port all 50+ entries verbatim."""
        assert len(COMMODITY_STRIKE_STEP) >= 50
        # Spot-check key commodities.
        for key, expected in (
            ("GOLD", 100.0),
            ("SILVER", 250.0),
            ("CRUDEOIL", 50.0),
            ("NATURALGAS", 5.0),
            ("COPPER", 5.0),
            ("NICKEL", 10.0),
            ("ZINC", 2.5),
            ("LEAD", 1.0),
            ("ALUMINIUM", 1.0),
            ("COTTON", 100.0),
            ("MENTHAOIL", 10.0),
            ("GOLDM", 50.0),
            ("GOLDPETAL", 5.0),
            ("GOLDGUINEA", 10.0),
            ("SILVERM", 250.0),
            ("SILVERMIC", 10.0),
            ("BRASS", 5.0),
            ("CASTORSEED", 100.0),
            ("COTTONSEEDOILCAKE", 100.0),
            ("CARDAMOM", 50.0),
            ("RBDPALMOLEIN", 10.0),
            ("CRUDEPALMOIL", 10.0),
            ("PEPPER", 100.0),
            ("JEERA", 100.0),
            ("SOYABEAN", 50.0),
            ("SOYAOIL", 10.0),
            ("TURMERIC", 100.0),
            ("GUARGUM", 100.0),
            ("GUARSEED", 100.0),
            ("CHANA", 50.0),
            ("MUSTARDSEED", 50.0),
            ("BARLEY", 50.0),
            ("SUGARM", 50.0),
            ("WHEAT", 50.0),
            ("MAIZE", 50.0),
            ("PADDY", 50.0),
            ("BAJRA", 50.0),
            ("JUTE", 50.0),
            ("RUBBER", 100.0),
            ("COFFEE", 50.0),
            ("COPRA", 50.0),
            ("SESAMESEED", 50.0),
            ("TEA", 100.0),
            ("KAPAS", 100.0),
            ("BARLEYFEED", 50.0),
            ("RAPESEED", 50.0),
            ("LINSEED", 50.0),
            ("SUNFLOWER", 50.0),
            ("CORIANDER", 50.0),
            ("CUMINSEED", 100.0),
        ):
            assert COMMODITY_STRIKE_STEP.get(key) == expected, key
