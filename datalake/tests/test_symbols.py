"""Tests for symbol normalization."""

from __future__ import annotations

from pathlib import Path

from datalake.symbols import (
    are_same_symbol,
    normalize_symbol,
    path_to_symbol,
    symbol_to_path,
)


class TestNormalizeSymbol:
    def test_uppercases(self) -> None:
        assert normalize_symbol("reliance") == "RELIANCE"
        assert normalize_symbol("Reliance") == "RELIANCE"
        assert normalize_symbol("RELIANCE") == "RELIANCE"

    def test_strips_whitespace(self) -> None:
        assert normalize_symbol("  RELIANCE  ") == "RELIANCE"
        assert normalize_symbol("\tTCS\n") == "TCS"

    def test_removes_eq_suffix(self) -> None:
        assert normalize_symbol("RELIANCE-EQ") == "RELIANCE"
        assert normalize_symbol("TCS-EQ") == "TCS"

    def test_removes_other_suffixes(self) -> None:
        assert normalize_symbol("RELIANCE-BE") == "RELIANCE"
        assert normalize_symbol("TCS-BL") == "TCS"
        assert normalize_symbol("INFY-MC") == "INFY"

    def test_underscore_suffix(self) -> None:
        assert normalize_symbol("RELIANCE_EQ") == "RELIANCE"
        assert normalize_symbol("TCS_BE") == "TCS"

    def test_empty_string(self) -> None:
        assert normalize_symbol("") == ""
        assert normalize_symbol("   ") == ""

    def test_no_change_for_clean_symbol(self) -> None:
        assert normalize_symbol("RELIANCE") == "RELIANCE"
        assert normalize_symbol("NIFTY") == "NIFTY"


class TestSymbolToPath:
    def test_basic(self) -> None:
        assert symbol_to_path("RELIANCE") == "symbol=RELIANCE"
        assert symbol_to_path("reliance") == "symbol=RELIANCE"

    def test_with_suffix(self) -> None:
        assert symbol_to_path("RELIANCE-EQ") == "symbol=RELIANCE"


class TestPathToSymbol:
    def test_basic(self) -> None:
        assert path_to_symbol("symbol=RELIANCE") == "RELIANCE"
        assert path_to_symbol("RELIANCE") == "RELIANCE"
        assert path_to_symbol("symbol=reliance") == "RELIANCE"

    def test_full_path(self) -> None:
        p = Path("market_data/equities/candles/timeframe=1m/symbol=RELIANCE/data.parquet")
        assert path_to_symbol(p) == "RELIANCE"


class TestAreSameSymbol:
    def test_same(self) -> None:
        assert are_same_symbol("RELIANCE", "reliance") is True
        assert are_same_symbol("RELIANCE-EQ", "RELIANCE") is True
        assert are_same_symbol("  TCS  ", "TCS") is True

    def test_different(self) -> None:
        assert are_same_symbol("RELIANCE", "TCS") is False
        assert are_same_symbol("RELIANCE", "RELIANCEBANK") is False
