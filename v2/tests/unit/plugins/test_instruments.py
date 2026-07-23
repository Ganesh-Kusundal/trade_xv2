"""Tests for DhanInstrumentAdapter CSV loading."""

from __future__ import annotations

import csv
import io
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from domain.enums import AssetClass, ExchangeId, InstrumentType, OptionType
from domain.value_objects import InstrumentId
from plugins.brokers.dhan.adapters.instruments import (
    DHAN_INSTRUMENT_CSV,
    DHAN_MCX_COMM_URL,
    DhanInstrumentAdapter,
)


@pytest.fixture
def mock_transport() -> MagicMock:
    t = MagicMock()
    t.get.return_value = {"data": []}
    return t


@pytest.fixture
def adapter(mock_transport: MagicMock) -> DhanInstrumentAdapter:
    return DhanInstrumentAdapter(transport=mock_transport)


SAMPLE_CSV = """\
SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS,SEM_TICK_SIZE,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE
RELIANCE-EQ,2885,NSE,E,EQ,1,0.05,,,, 
TCS-EQ,1234,NSE,E,EQ,1,0.05,,,, 
NIFTY24JULFUT,50000,NSE,D,FUTIDX,50,0.05,2024-07-25,,,
NIFTY24JUL24000CE,50001,NSE,D,OPTIDX,50,0.05,2024-07-25,24000,CE
GOLD24JULFUT,60001,MCX,M,FUTCOM,100,1,2024-07-25,,,
CRUDEOIL24JULFUT,60002,MCX,M,FUTCOM,100,1,2024-07-25,,,
"""

SAMPLE_MCX_CSV = """\
SEGMENT,SECURITY_ID,SYMBOL_NAME,INSTRUMENT,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,DISPLAY_NAME,LOT_SIZE,TICK_SIZE
M,70001,GOLD,FUT,2024-07-25,,, GOLD24JULFUT,100,1
M,70002,GOLD,OPT,2024-07-25,72000,CE,GOLD24JUL24000CE,100,1
M,70003,GOLD,OPT,2024-07-25,72000,PE,GOLD24JUL24000PE,100,1
M,12345,NSE,EQ,NSE,,,
"""


class TestInstrumentAdapterConstants:
    def test_csv_url(self) -> None:
        assert DHAN_INSTRUMENT_CSV == "https://images.dhan.co/api-data/api-scrip-master.csv"

    def test_mcx_url(self) -> None:
        assert DHAN_MCX_COMM_URL == "https://api.dhan.co/v2/instrument/MCX_COMM"


class TestCsvParsing:
    def test_parse_csv_equity(self, adapter: DhanInstrumentAdapter) -> None:
        instruments = adapter._parse_csv_to_instruments(SAMPLE_CSV)
        # G10: -EQ suffix is stripped from equity symbols
        equity = [i for i in instruments if i.symbol == "RELIANCE"]
        assert len(equity) == 1
        inst = equity[0]
        assert inst.instrument_id == InstrumentId.parse("NSE:RELIANCE")
        assert inst.exchange == ExchangeId.NSE
        assert inst.asset_class == AssetClass.EQUITY
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.currency == "INR"

    def test_parse_csv_futures(self, adapter: DhanInstrumentAdapter) -> None:
        instruments = adapter._parse_csv_to_instruments(SAMPLE_CSV)
        fut = [i for i in instruments if "FUT" in i.symbol]
        assert len(fut) >= 1
        nifty_fut = [i for i in fut if "NIFTY" in i.symbol][0]
        assert nifty_fut.instrument_type == InstrumentType.FUTURE
        assert nifty_fut.exchange == ExchangeId.NFO
        assert nifty_fut.expiry is not None

    def test_parse_csv_options(self, adapter: DhanInstrumentAdapter) -> None:
        instruments = adapter._parse_csv_to_instruments(SAMPLE_CSV)
        opts = [i for i in instruments if i.instrument_type == InstrumentType.OPTION]
        assert len(opts) >= 1
        nifty_ce = [i for i in opts if i.option_type == OptionType.CALL][0]
        assert nifty_ce.strike == Decimal("24000")
        assert nifty_ce.expiry is not None

    def test_parse_csv_skips_empty_symbol(self, adapter: DhanInstrumentAdapter) -> None:
        csv_content = "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_INSTRUMENT_NAME,SEM_LOT_UNITS,SEM_TICK_SIZE,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE\n,1234,NSE,E,EQ,1,0.05,,,,"
        instruments = adapter._parse_csv_to_instruments(csv_content)
        assert len(instruments) == 0

    def test_parse_csv_registers_wire(self, adapter: DhanInstrumentAdapter) -> None:
        adapter._parse_csv_to_instruments(SAMPLE_CSV)
        # G10: -EQ suffix is stripped, so instrument ID is NSE:RELIANCE
        iid = InstrumentId.parse("NSE:RELIANCE")
        sec_id = adapter._wire.security_id(iid)
        assert sec_id == "2885"


class TestCache:
    def test_cleanup_old_cache(self, adapter: DhanInstrumentAdapter) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            old_file = cache_dir / "dhan-instruments-2020-01-01.csv"
            old_file.write_text("old")
            import os
            os.utime(old_file, (0, 0))

            adapter._cleanup_old_cache(cache_dir)
            assert not old_file.exists()

    def test_cleanup_keeps_recent(self, adapter: DhanInstrumentAdapter) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            recent_file = cache_dir / "dhan-instruments-2025-01-01.csv"
            recent_file.write_text("recent")

            adapter._cleanup_old_cache(cache_dir)
            assert recent_file.exists()


class TestMCXSupplement:
    def test_mcx_row_to_instrument(self, adapter: DhanInstrumentAdapter) -> None:
        row = {
            "SEGMENT": "M",
            "SECURITY_ID": "70001",
            "SYMBOL_NAME": "GOLD",
            "INSTRUMENT": "FUT",
            "SM_EXPIRY_DATE": "2024-07-25",
            "STRIKE_PRICE": "",
            "OPTION_TYPE": "",
            "DISPLAY_NAME": "GOLD24JULFUT",
            "LOT_SIZE": "100",
            "TICK_SIZE": "1",
        }
        inst = adapter._mcx_row_to_instrument(row)
        assert inst is not None
        assert inst.exchange == ExchangeId.MCX
        assert inst.asset_class == AssetClass.COMMODITY
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.symbol == "GOLD-25Jul2024-FUT"
        assert adapter._wire.security_id(inst.instrument_id) == "70001"

    def test_mcx_option(self, adapter: DhanInstrumentAdapter) -> None:
        row = {
            "SEGMENT": "M",
            "SECURITY_ID": "70002",
            "SYMBOL_NAME": "GOLD",
            "INSTRUMENT": "OPT",
            "SM_EXPIRY_DATE": "2024-07-25",
            "STRIKE_PRICE": "72000",
            "OPTION_TYPE": "CE",
            "DISPLAY_NAME": "GOLD24JUL24000CE",
            "LOT_SIZE": "100",
            "TICK_SIZE": "1",
        }
        inst = adapter._mcx_row_to_instrument(row)
        assert inst is not None
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.option_type == OptionType.CALL
        assert inst.strike == Decimal("72000")
        assert "CE" in inst.symbol

    def test_mcx_fetch_skips_non_mcx(self, adapter: DhanInstrumentAdapter) -> None:
        csv_content = """\
SEGMENT,SECURITY_ID,SYMBOL_NAME,INSTRUMENT,SM_EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,DISPLAY_NAME,LOT_SIZE,TICK_SIZE
E,1234,RELIANCE,EQ,,,RELIANCE-EQ,1,0.05
M,70001,GOLD,FUT,2024-07-25,,, GOLD24JULFUT,100,1
"""
        with patch.object(adapter, "_download_csv", return_value=csv_content):
            instruments = adapter._fetch_mcx_supplement()
            assert len(instruments) == 1
            assert instruments[0].exchange == ExchangeId.MCX


class TestLoadFromCSV:
    # SAMPLE_CSV is a deliberately tiny fixture (6 rows); lower the real
    # ~220k-row production floor so these tests exercise caching/download
    # mechanics without needing a full-size fixture.
    @patch("plugins.brokers.dhan.adapters.instruments.MIN_DHAN_INSTRUMENTS", 3)
    @patch("plugins.brokers.dhan.adapters.instruments.DhanInstrumentAdapter._download_csv")
    def test_load_from_csv_success(self, mock_download: MagicMock, adapter: DhanInstrumentAdapter) -> None:
        mock_download.return_value = SAMPLE_CSV
        instruments = adapter.load_from_csv()
        assert len(instruments) >= 5
        assert mock_download.called

    @patch("plugins.brokers.dhan.adapters.instruments.MIN_DHAN_INSTRUMENTS", 3)
    @patch("plugins.brokers.dhan.adapters.instruments.DhanInstrumentAdapter._download_csv")
    def test_load_from_csv_caches_file(self, mock_download: MagicMock, adapter: DhanInstrumentAdapter, tmp_path: Path) -> None:
        mock_download.return_value = SAMPLE_CSV
        with patch("plugins.brokers.dhan.adapters.instruments._RUNTIME_DIR", tmp_path):
            adapter.load_from_csv()

        from datetime import date
        today = date.today().isoformat()
        cache_path = tmp_path / f"dhan-instruments-{today}.csv"
        assert cache_path.exists()
        assert cache_path.stat().st_size > 0

    @patch("plugins.brokers.dhan.adapters.instruments.MIN_DHAN_INSTRUMENTS", 3)
    def test_load_from_csv_uses_valid_cache(self, adapter: DhanInstrumentAdapter, tmp_path: Path) -> None:
        from datetime import date
        today = date.today().isoformat()
        cache_path = tmp_path / f"dhan-instruments-{today}.csv"
        cache_path.write_text(SAMPLE_CSV)

        # _download_csv is also used (unconditionally) for the MCX supplement
        # fetch — that failure path is already non-fatal, so raising here just
        # proves the *main* master came from cache, not a fresh download.
        with patch("plugins.brokers.dhan.adapters.instruments._RUNTIME_DIR", tmp_path):
            with patch.object(adapter, "_download_csv", side_effect=Exception("network error")):
                instruments = adapter.load_from_csv()
        assert len(instruments) >= 5

    def test_load_from_csv_rejects_undersized_download(self, adapter: DhanInstrumentAdapter, tmp_path: Path) -> None:
        """A download smaller than MIN_DHAN_INSTRUMENTS is corrupt/wrong — reject it, don't cache it."""
        with patch("plugins.brokers.dhan.adapters.instruments._RUNTIME_DIR", tmp_path):
            with patch.object(adapter, "_download_csv", return_value=SAMPLE_CSV):
                with pytest.raises(ValueError, match="too few rows"):
                    adapter.load_from_csv()

        from datetime import date
        today = date.today().isoformat()
        assert not (tmp_path / f"dhan-instruments-{today}.csv").exists()

    def test_load_from_csv_discards_undersized_cache_and_redownloads(
        self, adapter: DhanInstrumentAdapter, tmp_path: Path
    ) -> None:
        """A stray/stale small cache file (like today's incident) must not be trusted."""
        from datetime import date

        tiny_cache = (
            "SEM_TRADING_SYMBOL,SEM_SMST_SECURITY_ID,SEM_EXM_EXCH_ID,SEM_SEGMENT,"
            "SEM_INSTRUMENT_NAME,SEM_LOT_UNITS,SEM_TICK_SIZE,SEM_EXPIRY_DATE,"
            "SEM_STRIKE_PRICE,SEM_OPTION_TYPE\nFAKE-EQ,1234,NSE,E,EQ,1,0.05,,,\n"
        )
        today = date.today().isoformat()
        cache_path = tmp_path / f"dhan-instruments-{today}.csv"
        cache_path.write_text(tiny_cache)

        with patch("plugins.brokers.dhan.adapters.instruments._RUNTIME_DIR", tmp_path):
            with patch("plugins.brokers.dhan.adapters.instruments.MIN_DHAN_INSTRUMENTS", 5):
                with patch.object(adapter, "_download_csv", return_value=SAMPLE_CSV) as mock_download:
                    instruments = adapter.load_from_csv()
                    assert mock_download.called
        assert len(instruments) >= 5
        # the stale/tiny cache file must have been replaced by the real download
        assert cache_path.read_text() == SAMPLE_CSV



class TestLoadInstruments:
    @patch.object(DhanInstrumentAdapter, "load_from_csv")
    def test_load_instruments_tries_csv(self, mock_csv: MagicMock, adapter: DhanInstrumentAdapter) -> None:
        mock_csv.return_value = []
        adapter.load_instruments()
        assert mock_csv.called

    @patch.object(DhanInstrumentAdapter, "load_from_csv", side_effect=ValueError("csv failed"))
    def test_load_instruments_propagates_csv_failure(self, mock_csv: MagicMock, adapter: DhanInstrumentAdapter) -> None:
        """No REST fallback anymore — a bad/undersized CSV must fail loudly, not silently degrade."""
        with pytest.raises(ValueError, match="csv failed"):
            adapter.load_instruments()


class TestSearch:
    def test_search_by_symbol(self, adapter: DhanInstrumentAdapter) -> None:
        adapter._parse_csv_to_instruments(SAMPLE_CSV)
        results = adapter.search("RELIANCE")
        assert len(results) == 1
        # G10: -EQ suffix is stripped from equity symbols
        assert results[0].symbol == "RELIANCE"

    def test_search_by_instrument_id(self, adapter: DhanInstrumentAdapter) -> None:
        adapter._parse_csv_to_instruments(SAMPLE_CSV)
        results = adapter.search("NSE:TCS")
        assert len(results) == 1
        # G10: -EQ suffix is stripped from equity symbols
        assert results[0].symbol == "TCS"

    def test_search_returns_empty(self, adapter: DhanInstrumentAdapter) -> None:
        adapter._parse_csv_to_instruments(SAMPLE_CSV)
        results = adapter.search("NONEXISTENT")
        assert len(results) == 0


class TestResolve:
    def test_resolve_existing(self, adapter: DhanInstrumentAdapter) -> None:
        adapter._parse_csv_to_instruments(SAMPLE_CSV)
        # G10: -EQ suffix is stripped, so instrument ID is NSE:RELIANCE
        inst = adapter.resolve(InstrumentId.parse("NSE:RELIANCE"))
        assert inst is not None
        assert inst.symbol == "RELIANCE"

    def test_resolve_missing(self, adapter: DhanInstrumentAdapter) -> None:
        inst = adapter.resolve(InstrumentId.parse("NSE:MISSING"))
        assert inst is None
