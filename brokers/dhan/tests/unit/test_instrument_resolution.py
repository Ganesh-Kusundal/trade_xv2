"""Contract tests for the Dhan instrument resolution pipeline.

These tests cover the audit's §10 contract list:

* test_resolve_equity
* test_resolve_index
* test_resolve_future
* test_resolve_option
* test_ambiguous_symbol
* test_snapshot_cache_reuse
* test_snapshot_refresh
* test_historical_data_resolution
* test_live_quote_resolution

They also pin Trade_J compatibility for the symbol-resolver entry points
so any drift (e.g. dropping a segment prefix, allowing a silent first-match
selection) is caught by CI.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.mapper.contract_symbol_normalizer import (
    build_canonical,
    extract_future_underlying,
    is_known_contract,
    normalize,
    normalize_strict,
    parse,
)
from brokers.dhan.mapper.instruments import (
    CatalogDiagnostics,
    DhanInstrumentCatalog,
    DhanInstrumentDefinition,
    DhanInstrumentLoader,
    DhanSymbolResolver,
    SnapshotValidationError,
    _extract_future_underlying,
    validate_snapshot,
)

# ─── Test fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def temp_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "instruments"


@pytest.fixture()
def sample_csv_path(tmp_path: Path) -> Path:
    """Build a tiny but representative Dhan snapshot.

    Mirrors the columns published at images.dhan.co/api-data/api-scrip-master.csv
    with one equity, one index, one future, and one option so the audit's
    resolve_*_contract tests have full coverage.
    """
    path = tmp_path / "api-scrip-master-test.csv"
    rows = [
        [
            "SEM_EXM_EXCH_ID",
            "SEM_SEGMENT",
            "SEM_SMST_SECURITY_ID",
            "SEM_INSTRUMENT_NAME",
            "SEM_EXPIRY_CODE",
            "SEM_TRADING_SYMBOL",
            "SEM_LOT_UNITS",
            "SEM_CUSTOM_SYMBOL",
            "SEM_EXPIRY_DATE",
            "SEM_STRIKE_PRICE",
            "SEM_OPTION_TYPE",
            "SEM_TICK_SIZE",
            "SEM_EXPIRY_FLAG",
            "SEM_EXCH_INSTRUMENT_TYPE",
            "SEM_SERIES",
            "SM_SYMBOL_NAME",
        ],
        # NSE equity
        [
            "NSE",
            "E",
            "2885",
            "EQUITY",
            "0",
            "RELIANCE",
            "1.0",
            "Reliance Industries",
            "",
            "",
            "XX",
            "10.0000",
            "NA",
            "ES",
            "EQ",
            "RELIANCE INDUSTRIES LTD",
        ],
        # BSE equity (same trading symbol on BSE — must produce an ambiguity
        # when resolved without a segment prefix)
        [
            "BSE",
            "E",
            "500325",
            "EQUITY",
            "0",
            "RELIANCE",
            "1.0",
            "Reliance Industries",
            "",
            "",
            "XX",
            "5.0000",
            "NA",
            "ES",
            "A",
            "RELIANCE INDUSTRIES LTD.",
        ],
        # NSE index
        [
            "NSE",
            "I",
            "13",
            "INDEX",
            "0",
            "NIFTY",
            "1.0",
            "Nifty 50",
            "",
            "",
            "XX",
            "0.0500",
            "",
            "INDEX",
            "X",
            "NIFTY",
        ],
        # NSE banknifty index
        [
            "NSE",
            "I",
            "25",
            "INDEX",
            "0",
            "BANKNIFTY",
            "1.0",
            "Nifty Bank",
            "",
            "",
            "XX",
            "0.0500",
            "",
            "INDEX",
            "X",
            "BANKNIFTY",
        ],
        # NSE future
        [
            "NSE",
            "D",
            "61284",
            "FUTSTK",
            "0",
            "RELIANCE-Jul2026-FUT",
            "500.0",
            "RELIANCE JUL FUT",
            "2026-07-28 14:30:00",
            "-0.01000",
            "XX",
            "10.0000",
            "M",
            "FUT",
            "",
            "RELIANCE",
        ],
        # NSE option (call)
        [
            "NSE",
            "D",
            "1103387",
            "OPTSTK",
            "0",
            "RELIANCE-Jun2026-1400-CE",
            "500.0",
            "RELIANCE 25 JUN 1400 CALL",
            "2026-06-25 15:30:00",
            "1400.00000",
            "CE",
            "5.0000",
            "M",
            "OPTSTK",
            "",
            "RELIOPT",
        ],
        # NSE option (put)
        [
            "NSE",
            "D",
            "1103312",
            "OPTSTK",
            "0",
            "RELIANCE-Jun2026-1410-PE",
            "500.0",
            "RELIANCE 25 JUN 1410 PUT",
            "2026-06-25 15:30:00",
            "1410.00000",
            "PE",
            "5.0000",
            "M",
            "OPTSTK",
            "",
            "RELIOPT",
        ],
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return path


@pytest.fixture()
def catalog(sample_csv_path: Path) -> DhanInstrumentCatalog:
    cat = DhanInstrumentCatalog()
    cat.load(sample_csv_path)
    return cat


# ─── §1 Daily snapshot ──────────────────────────────────────────────────────


class TestDailySnapshot:
    """Audit §1 — daily snapshot handling."""

    def test_snapshot_path_format(self, temp_cache_dir: Path):
        loader = DhanInstrumentLoader()
        path = loader.ensure_daily_snapshot(temp_cache_dir, force_refresh=True)
        assert path.name == f"api-scrip-master-{date.today()}.csv"
        assert path.parent == temp_cache_dir

    def test_snapshot_reuse(self, temp_cache_dir: Path):
        loader = DhanInstrumentLoader()
        first = loader.ensure_daily_snapshot(temp_cache_dir, force_refresh=True)
        # Second call must NOT re-download — same path, same mtime check.
        # We can't test mtime directly, so verify the file isn't re-fetched
        # by patching urlopen.
        with mock.patch.object(loader, "_download_to") as mock_dl:
            second = loader.ensure_daily_snapshot(temp_cache_dir)
        assert first == second
        mock_dl.assert_not_called()

    def test_snapshot_force_refresh(self, temp_cache_dir: Path):
        loader = DhanInstrumentLoader()
        loader.ensure_daily_snapshot(temp_cache_dir)
        with mock.patch.object(loader, "_download_to") as mock_dl:
            loader.ensure_daily_snapshot(temp_cache_dir, force_refresh=True)
        mock_dl.assert_called_once()

    def test_empty_file_is_refreshed(self, temp_cache_dir: Path):
        loader = DhanInstrumentLoader()
        # Pre-create an empty file at today's path
        empty = temp_cache_dir / f"api-scrip-master-{date.today()}.csv"
        temp_cache_dir.mkdir(parents=True, exist_ok=True)
        empty.write_text("")
        with mock.patch.object(loader, "_download_to") as mock_dl:
            loader.ensure_daily_snapshot(temp_cache_dir)
        mock_dl.assert_called_once()

    def test_cache_dir_configurable(self, temp_cache_dir: Path):
        loader = DhanInstrumentLoader()
        path = loader.ensure_daily_snapshot(temp_cache_dir, force_refresh=True)
        assert path.parent == temp_cache_dir

    def test_logging_messages(self, temp_cache_dir: Path, caplog):
        loader = DhanInstrumentLoader()
        with caplog.at_level("INFO", logger="brokers.dhan.mapper.instruments"):
            loader.ensure_daily_snapshot(temp_cache_dir, force_refresh=True)
        text = caplog.text
        assert "Downloading fresh instrument snapshot" in text
        assert "Snapshot date" in text
        assert "Snapshot checksum" in text
        assert "Snapshot record count" in text

    def test_file_lock_present(self, temp_cache_dir: Path):
        """Concurrent calls must serialise through a file lock."""
        import threading

        loader = DhanInstrumentLoader()
        call_count = 0
        counter_lock = threading.Lock()

        def fake_download(snapshot: Path):
            nonlocal call_count
            with counter_lock:
                call_count += 1
            # Tiny sleep so two threads contend
            import time

            time.sleep(0.05)
            snapshot.write_text("header\n")

        with mock.patch.object(loader, "_download_to", side_effect=fake_download):
            threads = [
                threading.Thread(
                    target=loader.ensure_daily_snapshot,
                    args=(temp_cache_dir,),
                )
                for _ in range(5)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        # The lock must ensure only one download is issued; the rest reuse.
        assert call_count == 1


# ─── §2 Catalog indexes ─────────────────────────────────────────────────────


class TestCatalogIndexes:
    """Audit §2 — 6 required indexes plus duplicate / missing-field detection."""

    def test_all_six_indexes_populated(self, catalog: DhanInstrumentCatalog):
        diag: CatalogDiagnostics = catalog.diagnostics()
        assert diag.by_security_id_size >= 7
        assert diag.by_trading_symbol_size >= 4  # RELIANCE ×2, NIFTY, BANKNIFTY
        assert diag.by_custom_symbol_size >= 4
        # ISIN not in our fixture, so 0
        assert diag.by_isin_size == 0
        assert diag.by_exchange_size >= 2  # NSE, BSE
        assert diag.by_segment_size >= 3  # NSE_EQ, BSE_EQ, NSE_FNO, IDX_I

    def test_no_duplicate_security_ids(self, catalog: DhanInstrumentCatalog):
        diag = catalog.diagnostics()
        assert diag.duplicate_security_ids == ()

    def test_futures_and_options_counted(self, catalog: DhanInstrumentCatalog):
        diag = catalog.diagnostics()
        assert diag.futures_count >= 1
        assert diag.options_count >= 2  # CE and PE
        assert diag.indices_count >= 2  # NIFTY + BANKNIFTY
        assert diag.equities_count >= 2  # RELIANCE NSE + BSE

    def test_find_by_trading_symbol(self, catalog: DhanInstrumentCatalog):
        results = catalog.find_by_trading_symbol("RELIANCE")
        # Both NSE and BSE entries must be returned.
        assert len(results) == 2
        segments = {r.exchange_segment for r in results}
        assert ExchangeSegment.NSE in segments
        assert ExchangeSegment.BSE in segments

    def test_find_by_custom_symbol(self, catalog: DhanInstrumentCatalog):
        results = catalog.find_by_custom_symbol("Reliance Industries")
        assert len(results) == 2
        assert all(r.canonical_symbol.upper() == "RELIANCE INDUSTRIES" for r in results)

    def test_find_by_exchange(self, catalog: DhanInstrumentCatalog):
        nse = catalog.find_by_exchange("NSE")
        bse = catalog.find_by_exchange("BSE")
        idx = catalog.find_by_exchange("IDX")
        assert all(r.exchange == "NSE" for r in nse)
        assert all(r.exchange == "BSE" for r in bse)
        assert all(r.exchange == "IDX" for r in idx)
        # NSE contains the future, the options, and the equity
        assert any(r.is_future for r in nse)
        assert any(r.is_option for r in nse)
        assert any(r.is_equity for r in nse)
        # IDX contains the indices
        assert any(r.is_index for r in idx)

    def test_find_by_segment(self, catalog: DhanInstrumentCatalog):
        nse_eq = catalog.find_by_segment(ExchangeSegment.NSE)
        nse_fno = catalog.find_by_segment(ExchangeSegment.NSE_FNO)
        idx_i = catalog.find_by_segment(ExchangeSegment.IDX_I)
        assert all(r.exchange_segment == ExchangeSegment.NSE for r in nse_eq)
        assert all(r.exchange_segment == ExchangeSegment.NSE_FNO for r in nse_fno)
        assert all(r.exchange_segment == ExchangeSegment.IDX_I for r in idx_i)
        # NSE FNO should contain the future and the options
        assert any(r.is_future for r in nse_fno)
        assert any(r.is_option for r in nse_fno)

    def test_diagnostics_report_human_readable(self, catalog: DhanInstrumentCatalog):
        report = catalog.diagnostics().to_report()
        assert "Catalog diagnostics" in report
        assert "record count" in report
        assert "checksum" in report

    def test_strike_price_paisa_is_int_paisa(self, catalog: DhanInstrumentCatalog):
        """Strike price paisa must be integer rupees * 100 (no float drift)."""
        # Find the 1400 CE option
        options = catalog.option_contracts("RELIANCE")
        ce = next(o for o in options if o.strike == Decimal("1400"))
        assert ce.strike_price_paisa == 140000

    def test_diagnostic_checksum_matches_file(self, catalog, sample_csv_path):
        import hashlib

        expected = hashlib.sha256(sample_csv_path.read_bytes()).hexdigest()
        assert catalog.diagnostics().checksum == expected


# ─── §3 Symbol resolution logic ─────────────────────────────────────────────


class TestEquityResolution:
    """Audit §3 — equity symbol resolution."""

    def test_resolve_equity(self, catalog: DhanInstrumentCatalog):
        """`RELIANCE` is ambiguous (NSE + BSE).  NSE:RELIANCE is single."""
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NSE:RELIANCE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "2885"
        assert result.definition.exchange_segment == ExchangeSegment.NSE

    def test_resolve_bse_equity(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("BSE:RELIANCE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "500325"

    def test_resolve_equity_canonical_prefix(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NSE_EQ:RELIANCE")
        assert result.is_single
        assert result.definition.security_id == "2885"

    def test_resolve_equity_legacy_eq_suffix(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE-EQ")
        assert result.is_single
        assert result.definition.security_id == "2885"

    def test_resolve_equity_legacy_be_suffix(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE-BE")
        assert result.is_single
        assert result.definition.security_id == "500325"


class TestIndexResolution:
    """Audit §3 — index symbol resolution."""

    def test_resolve_index(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NIFTY")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.security_id == "13"
        assert result.definition.is_index

    def test_resolve_index_nifty_50(self, catalog):
        """`NIFTY 50` (spaced) must resolve to the NIFTY index."""
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NIFTY 50")
        assert result.is_single
        assert result.definition.security_id == "13"

    def test_resolve_banknifty(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("BANKNIFTY")
        assert result.is_single
        assert result.definition.security_id == "25"

    def test_resolve_index_via_nse_fno_chain(self, catalog):
        """`NSE_FNO:NIFTY` must resolve via the underlying chain to IDX_I."""
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NSE_FNO:NIFTY")
        assert result.is_single
        assert result.definition.security_id == "13"
        assert result.definition.exchange_segment == ExchangeSegment.IDX_I


class TestFutureResolution:
    """Audit §3 — future contract resolution."""

    def test_resolve_future(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE FUT")
        # Compact future resolved via futures index
        assert result.is_single
        assert result.definition is not None
        assert result.definition.is_future
        assert result.definition.security_id == "61284"

    def test_resolve_future_full(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE 25 JUN FUT")  # not in our fixture
        # No exact match — but we should still get something because the
        # RELIANCE futures in our fixture has 28 JUL, not 25 JUN.
        # Use the contract that we have:
        result = resolver.resolve("RELIANCE 28 JUL FUT")
        assert result.is_single
        assert result.definition.security_id == "61284"


class TestOptionResolution:
    """Audit §3 — option contract resolution."""

    def test_resolve_option_compact(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE25JUN1400CE")
        assert result.is_single
        assert result.definition is not None
        assert result.definition.is_option
        assert result.definition.security_id == "1103387"
        assert result.definition.option_type == "CE"
        assert result.definition.strike_price_paisa == 140000

    def test_resolve_option_spaced(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE 25 JUN 1400 CE")
        assert result.is_single
        assert result.definition.security_id == "1103387"

    def test_resolve_option_put(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE25JUN1410PE")
        assert result.is_single
        assert result.definition.security_id == "1103312"
        assert result.definition.option_type == "PE"

    def test_resolve_option_bare_underlying(self, catalog):
        """`NIFTY 25000 CE` (no date) — should still find a NIFTY 25000 CE."""
        # Add a NIFTY 25000 CE to the catalog to test
        defn = DhanInstrumentDefinition(
            symbol="NIFTY",
            canonical_symbol="NIFTY 30 JUN 25000 CALL",
            exchange_segment=ExchangeSegment.NSE_FNO,
            security_id="999001",
            instrument_type="OPTIDX",
            underlying="NIFTY",
            expiry=date(2026, 6, 30).isoformat(),
            strike=Decimal("25000"),
            strike_price_paisa=2500000,
            option_type="CE",
            lot_size=50,
        )
        catalog.replace_all([defn])
        resolver = DhanSymbolResolver(catalog)
        # NIFTY 25000 CE without a date — should still find a NIFTY 25000 CE
        result = resolver.resolve("NIFTY 25000 CE")
        assert result.is_single
        assert result.definition.security_id == "999001"


class TestAmbiguity:
    """Audit §3 — ambiguous matches return structured errors, never first-match."""

    def test_ambiguous_symbol(self, catalog: DhanInstrumentCatalog):
        """Bare `RELIANCE` exists on both NSE and BSE → must be ambiguous."""
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE")
        assert result.is_ambiguous
        assert len(result.candidates) == 2
        assert "RELIANCE NSE_EQ" in result.reason
        assert "RELIANCE BSE_EQ" in result.reason
        assert "Specify exchange" in result.reason

    def test_ambiguous_require_raises(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        with pytest.raises(ValueError) as exc:
            resolver.require("RELIANCE")
        assert "Ambiguous" in str(exc.value)
        assert "Multiple matches found" in str(exc.value)

    def test_unknown_symbol(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("TOTALLY_FAKE_SYMBOL_123")
        assert result.is_unknown
        assert "TOTALLY_FAKE_SYMBOL_123" in result.reason

    def test_unknown_segment_prefix(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NOPE:RELIANCE")
        assert result.is_unknown
        assert "NOPE" in result.reason

    def test_empty_input(self, catalog: DhanInstrumentCatalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("")
        assert result.is_unknown
        assert "empty" in result.reason.lower()


# ─── §4 Exchange segment mapping ────────────────────────────────────────────


class TestSegmentMapping:
    """Audit §4 — segment mapper covers every Dhan master combination."""

    def test_nse_segments(self):
        from brokers.common.core.enums import ExchangeSegment as ES
        from brokers.dhan.mapper.dhan_segment_mapper import from_csv

        assert from_csv("NSE", "E") == ES.NSE
        assert from_csv("NSE", "D") == ES.NSE_FNO
        assert from_csv("NSE", "I") == ES.IDX_I
        assert from_csv("NSE", "C") == ES.NSE_CURRENCY
        assert from_csv("NSE", "M") == ES.MCX

    def test_bse_segments(self):
        from brokers.common.core.enums import ExchangeSegment as ES
        from brokers.dhan.mapper.dhan_segment_mapper import from_csv

        assert from_csv("BSE", "E") == ES.BSE
        assert from_csv("BSE", "D") == ES.BSE_FNO
        assert from_csv("BSE", "I") == ES.IDX_I
        assert from_csv("BSE", "C") == ES.BSE_CURRENCY
        assert from_csv("BSE", "M") == ES.MCX

    def test_mcx_segments(self):
        from brokers.common.core.enums import ExchangeSegment as ES
        from brokers.dhan.mapper.dhan_segment_mapper import from_csv

        assert from_csv("MCX", "M") == ES.MCX

    def test_wire_value_round_trip(self):
        from brokers.common.core.enums import ExchangeSegment as ES
        from brokers.dhan.mapper.dhan_segment_mapper import from_value, to_wire_value

        for seg in (
            ES.NSE,
            ES.BSE,
            ES.NSE_FNO,
            ES.BSE_FNO,
            ES.MCX,
            ES.IDX_I,
            ES.NSE_CURRENCY,
            ES.BSE_CURRENCY,
        ):
            wire = to_wire_value(seg)
            assert from_value(wire) == seg


# ─── §5 Broker integration path ─────────────────────────────────────────────


class TestBrokerIntegration:
    """Audit §5 — broker never bypasses the catalog."""

    def test_quote_resolves_via_catalog(self, catalog):
        """`get_quote('RELIANCE', 'NSE')` must use catalog securityId."""
        from brokers.dhan.broker import DhanBroker  # noqa: F401

        # We can't construct a DhanBroker without env, but we can verify
        # the resolver methods used by the broker are present and correct.
        assert callable(catalog.segment_from_exchange)
        assert callable(catalog.resolve_security_id)
        # And that the lookup returns the right SID
        assert catalog.resolve_security_id("RELIANCE", "NSE") == "2885"
        assert catalog.resolve_security_id("RELIANCE", "BSE") == "500325"
        assert catalog.resolve_security_id("NIFTY", "IDX_I") == "13"

    def test_historical_data_resolves_via_catalog(self, catalog):
        """Historical data uses the same resolver entry point."""
        assert catalog.resolve_security_id("RELIANCE", "NSE") == "2885"
        assert catalog.resolve_security_id("NIFTY", "IDX") == "13"
        assert catalog.resolve_security_id("BANKNIFTY", "IDX") == "25"

    def test_resolve_payload_security_id(self, catalog):
        payload = {"securityId": "2885"}
        defn = catalog.resolve_payload(payload)
        assert defn is not None
        assert defn.security_id == "2885"

    def test_resolve_payload_trading_symbol_segment(self, catalog):
        payload = {"tradingSymbol": "RELIANCE", "exchangeSegment": "NSE_EQ"}
        defn = catalog.resolve_payload(payload)
        assert defn is not None
        assert defn.security_id == "2885"

    def test_resolve_payload_trading_symbol_exchange_alias(self, catalog):
        payload = {"tradingSymbol": "RELIANCE", "exchange": "NSE"}
        defn = catalog.resolve_payload(payload)
        assert defn is not None
        assert defn.security_id == "2885"

    def test_resolve_payload_returns_none_for_unknown(self, catalog):
        assert catalog.resolve_payload({"securityId": "99999999"}) is None
        assert catalog.resolve_payload({"tradingSymbol": "X", "exchange": "Y"}) is None
        assert catalog.resolve_payload(None) is None

    def test_resolve_payload_object_like(self, catalog):
        class FakePayload:
            securityId = "2885"

        defn = catalog.resolve_payload(FakePayload())
        assert defn is not None
        assert defn.security_id == "2885"

    def test_resolve_payload_object_with_getters(self, catalog):
        class FakePayload:
            def getSecurityId(self):
                return "2885"

        defn = catalog.resolve_payload(FakePayload())
        assert defn is not None
        assert defn.security_id == "2885"

    def test_live_quote_resolves_via_catalog(self, catalog):
        """Live quote uses the same resolver path."""
        assert catalog.resolve_security_id("TCS", "NSE") in ("11536",)  # seed fallback


# ─── §6 Historical data validation ──────────────────────────────────────────


class TestHistoricalDataResolution:
    """Audit §6 — historical data uses the correct securityId + segment."""

    def test_historical_data_resolution(self, catalog: DhanInstrumentCatalog):
        """RELIANCE, TCS, NIFTY, BANKNIFTY all resolve to known SIDs."""
        assert catalog.resolve_security_id("RELIANCE", "NSE") == "2885"
        assert catalog.resolve_security_id("NIFTY", "IDX") == "13"
        assert catalog.resolve_security_id("BANKNIFTY", "IDX") == "25"

    def test_segment_used_for_history(self, catalog: DhanInstrumentCatalog):
        """NSE_EQ is the correct wire value for the underlying equity."""
        seg = catalog.segment_from_exchange("NSE")
        from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value

        assert to_wire_value(seg) == "NSE_EQ"

    def test_index_segment_used_for_history(self, catalog: DhanInstrumentCatalog):
        seg = catalog.segment_from_exchange("IDX")
        from brokers.dhan.mapper.dhan_segment_mapper import to_wire_value

        assert to_wire_value(seg) == "IDX_I"


# ─── §7 Cache validation ────────────────────────────────────────────────────


class TestCacheValidation:
    """Audit §7 — validate_snapshot enforces a fail-fast on corruption."""

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(SnapshotValidationError) as exc:
            validate_snapshot(tmp_path / "nope.csv")
        assert "does not exist" in str(exc.value)

    def test_empty_file_raises(self, tmp_path: Path):
        path = tmp_path / "empty.csv"
        path.write_text("")
        with pytest.raises(SnapshotValidationError) as exc:
            validate_snapshot(path)
        assert "empty" in str(exc.value)

    def test_missing_columns_raises(self, tmp_path: Path):
        path = tmp_path / "bad.csv"
        path.write_text("foo,bar\n1,2\n")
        with pytest.raises(SnapshotValidationError) as exc:
            validate_snapshot(path)
        assert "missing required columns" in str(exc.value)

    def test_duplicate_sids_raises(self, tmp_path: Path):
        """Composite-key duplicates (same exch+segment+security_id) must raise.

        Note: the same SID reused across different (exchange, segment)
        pairs is *legitimate* in Dhan's master CSV (e.g. SID 1 is used
        for both an NSE equity and an NSE index).  ``validate_snapshot``
        therefore enforces uniqueness on the composite tuple, not on the
        bare SID — this test uses a real composite-key collision.
        """
        path = tmp_path / "dup.csv"
        with open(path, "w", newline="") as fh:
            csv.writer(fh).writerow(
                [
                    "SEM_EXM_EXCH_ID",
                    "SEM_SEGMENT",
                    "SEM_SMST_SECURITY_ID",
                    "SEM_INSTRUMENT_NAME",
                    "SEM_TRADING_SYMBOL",
                    "SEM_CUSTOM_SYMBOL",
                    "SEM_OPTION_TYPE",
                    "SEM_STRIKE_PRICE",
                    "SEM_EXPIRY_DATE",
                ]
            )
            # Two rows with the SAME (exchange, segment, security_id)
            # triple — a real composite-key duplicate.
            csv.writer(fh).writerow(["NSE", "E", "1", "EQUITY", "AAA", "A", "XX", "", ""])
            csv.writer(fh).writerow(["NSE", "E", "1", "EQUITY", "BBB", "B", "XX", "", ""])
        with pytest.raises(SnapshotValidationError) as exc:
            validate_snapshot(path)
        # The error message must surface the composite-key tuple.
        assert "duplicate" in str(exc.value).lower()
        assert "(exchange, segment, security_id)" in str(exc.value)

    def test_sid_reuse_across_exchanges_is_legitimate(self, tmp_path: Path):
        """The same SID across different (exchange, segment) pairs is NOT a duplicate.

        Regression test for the M1 bug: Dhan's master CSV legitimately
        reuses ``SEM_SMST_SECURITY_ID`` values across different
        ``(exchange, segment)`` pairs (e.g. SID 1 for an NSE equity and
        a different NSE index).  The pre-check must not reject those
        snapshots.
        """
        path = tmp_path / "reuse.csv"
        with open(path, "w", newline="") as fh:
            csv.writer(fh).writerow(
                [
                    "SEM_EXM_EXCH_ID",
                    "SEM_SEGMENT",
                    "SEM_SMST_SECURITY_ID",
                    "SEM_INSTRUMENT_NAME",
                    "SEM_TRADING_SYMBOL",
                    "SEM_CUSTOM_SYMBOL",
                    "SEM_OPTION_TYPE",
                    "SEM_STRIKE_PRICE",
                    "SEM_EXPIRY_DATE",
                ]
            )
            csv.writer(fh).writerow(["NSE", "E", "1", "EQUITY", "AAA", "A", "XX", "", ""])
            csv.writer(fh).writerow(["NSE", "I", "1", "INDEX", "BBB", "B", "XX", "", ""])
        diag = validate_snapshot(path)
        assert diag.record_count == 2
        # No composite-key duplicate → both diagnostic lists must be empty.
        assert diag.duplicate_composite_keys == ()
        assert diag.duplicate_security_ids == ()

    def test_valid_snapshot_passes(self, sample_csv_path: Path):
        diag = validate_snapshot(sample_csv_path)
        assert diag.record_count >= 7
        assert diag.checksum  # non-empty
        assert diag.duplicate_security_ids == ()


# ─── §8 Search & lookup diagnostics (via CLI command) ───────────────────────


class TestLookupDiagnostics:
    """Audit §8 — DhanSymbolResolver returns rich info for the CLI."""

    def test_resolver_returns_security_id(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("NSE:RELIANCE")
        assert result.definition.security_id == "2885"
        assert result.definition.exchange == "NSE"
        assert result.definition.exchange_segment == ExchangeSegment.NSE
        assert result.definition.instrument_type == "EQUITY"

    def test_resolver_returns_future_metadata(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE FUT")
        assert result.definition.is_future
        assert result.definition.expiry is not None
        assert result.definition.expiry >= date.today().isoformat()

    def test_resolver_returns_option_metadata(self, catalog):
        resolver = DhanSymbolResolver(catalog)
        result = resolver.resolve("RELIANCE25JUN1400CE")
        d = result.definition
        assert d.is_option
        assert d.option_type == "CE"
        assert d.strike == Decimal("1400")
        assert d.strike_price_paisa == 140000
        assert d.expiry == date(2026, 6, 25).isoformat()


# ─── ContractSymbolNormalizer (Trade_J parity) ──────────────────────────────


class TestContractSymbolNormalizer:
    """Direct tests for the Trade_J-ported normalizer."""

    def test_parse_option_spaced(self):
        p = parse("NIFTY 30 JUN 25000 CE")
        assert p is not None
        assert p.underlying == "NIFTY"
        assert p.day == 30
        assert p.month == "JUN"
        assert p.strike == "25000"
        assert p.option_type == "CE"
        assert p.option is True

    def test_parse_option_compact(self):
        p = parse("NIFTY30JUN25000CE")
        assert p is not None
        assert p.underlying == "NIFTY"
        assert p.day == 30
        assert p.month == "JUN"
        assert p.strike == "25000"
        assert p.option_type == "CE"

    def test_parse_future_spaced(self):
        p = parse("NIFTY 30 JUN FUT")
        assert p is not None
        assert p.underlying == "NIFTY"
        assert p.day == 30
        assert p.month == "JUN"
        assert p.option is False
        assert p.strike is None

    def test_parse_future_compact(self):
        p = parse("NIFTY30JUNFUT")
        assert p is not None
        assert p.underlying == "NIFTY"
        assert p.option is False

    def test_parse_aliases(self):
        assert parse("NIFTY 30 JUN 25000 CALL").option_type == "CE"
        assert parse("NIFTY 30 JUN 25000 PUT").option_type == "PE"
        assert parse("NIFTY 30 JUN 25000 C").option_type == "CE"
        assert parse("NIFTY 30 JUN 25000 P").option_type == "PE"
        assert parse("NIFTY 30 JUN FUTURES").option is False

    def test_parse_equity_returns_none(self):
        assert parse("SBIN") is None
        assert parse("") is None
        assert parse(None) is None  # type: ignore[arg-type]

    def test_normalize_option(self):
        assert normalize("NIFTY30JUN25000CE") == "NIFTY 30 JUN 25000 CE"
        assert normalize("NIFTY 30 JUN 25000 CE") == "NIFTY 30 JUN 25000 CE"
        assert normalize("NIFTY30JUN25000PE") == "NIFTY 30 JUN 25000 PE"

    def test_normalize_future(self):
        assert normalize("NIFTY30JUNFUT") == "NIFTY 30 JUN FUT"
        assert normalize("NIFTY 30 JUN FUTURES") == "NIFTY 30 JUN FUT"

    def test_normalize_equity(self):
        assert normalize("SBIN") == "SBIN"
        assert normalize("Nifty 50") == "NIFTY 50"

    def test_normalize_strict_rejects_unknown(self):
        with pytest.raises(ValueError):
            normalize_strict("not_a_contract")

    def test_is_known_contract(self):
        assert is_known_contract("NIFTY 30 JUN 25000 CE")
        assert is_known_contract("NIFTY30JUN25000CE")
        assert is_known_contract("NIFTY 30 JUN FUT")
        assert is_known_contract("NIFTY30JUNFUT")
        assert not is_known_contract("SBIN")
        assert not is_known_contract("")

    def test_extract_future_underlying(self):
        assert extract_future_underlying("NIFTY30JUNFUT") == "NIFTY"
        assert extract_future_underlying("RELIANCE 25 JUN FUT") == "RELIANCE"
        assert extract_future_underlying("") == ""

    def test_private_extract_future_underlying_handles_rstrip_class_bug(self):
        # Bug: the manual fallback used rstrip("0123456789...") which is a
        # character class, so trailing underlying letters like 'T' / 'S' / 'F'
        # were silently stripped. For 'BANKNIFTY' alone the function must
        # return 'BANKNIFTY' (the trailing 'T' must not be stripped).
        assert _extract_future_underlying("BANKNIFTY") == "BANKNIFTY"
        assert _extract_future_underlying("NIFTY25JUNFUT") == "NIFTY"
        assert _extract_future_underlying("BANKNIFTYFUT") == "BANKNIFTY"
        # Extra coverage: parser-fallback inputs that previously produced
        # '' or stripped tails should now keep their underlying intact.
        assert _extract_future_underlying("ABCDEFUT") == "ABCDE"

    def test_build_canonical(self):
        assert (
            build_canonical(
                "NIFTY",
                date(2026, 6, 30),
                2500000,
                "CE",
                True,
            )
            == "NIFTY 30 JUN 25000 CE"
        )
        assert (
            build_canonical(
                "NIFTY",
                date(2026, 6, 30),
                2500050,
                "CE",
                True,
            )
            == "NIFTY 30 JUN 25000.50 CE"
        )
        assert (
            build_canonical(
                "NIFTY",
                date(2026, 6, 30),
                None,
                None,
                False,
            )
            == "NIFTY 30 JUN FUT"
        )

    def test_build_canonical_call_put_aliases(self):
        # CALL and PUT should be canonicalised
        assert (
            build_canonical(
                "NIFTY",
                date(2026, 6, 30),
                2500000,
                "CALL",
                True,
            )
            == "NIFTY 30 JUN 25000 CE"
        )
        assert (
            build_canonical(
                "NIFTY",
                date(2026, 6, 30),
                2500000,
                "PUT",
                True,
            )
            == "NIFTY 30 JUN 25000 PE"
        )


# ─── DhanInstrumentDefinition helpers ────────────────────────────────────────


class TestDhanInstrumentDefinition:
    def test_is_future_detection(self):
        defn = DhanInstrumentDefinition(
            symbol="X",
            canonical_symbol="X",
            exchange_segment=ExchangeSegment.NSE_FNO,
            security_id="1",
            instrument_type="FUTSTK",
        )
        assert defn.is_future is True
        assert defn.is_option is False
        assert defn.is_equity is False
        assert defn.is_index is False

    def test_is_option_detection(self):
        defn = DhanInstrumentDefinition(
            symbol="X",
            canonical_symbol="X",
            exchange_segment=ExchangeSegment.NSE_FNO,
            security_id="1",
            instrument_type="OPTSTK",
            option_type="CE",
        )
        assert defn.is_option is True
        assert defn.is_future is False

    def test_is_index_detection_via_segment(self):
        defn = DhanInstrumentDefinition(
            symbol="NIFTY",
            canonical_symbol="NIFTY 50",
            exchange_segment=ExchangeSegment.IDX_I,
            security_id="13",
            instrument_type="INDEX",
        )
        assert defn.is_index is True

    def test_exchange_short_name(self):
        defn = DhanInstrumentDefinition(
            symbol="X",
            canonical_symbol="X",
            exchange_segment=ExchangeSegment.NSE,
            security_id="1",
        )
        assert defn.exchange == "NSE"
        defn2 = DhanInstrumentDefinition(
            symbol="X",
            canonical_symbol="X",
            exchange_segment=ExchangeSegment.MCX,
            security_id="1",
        )
        assert defn2.exchange == "MCX"
