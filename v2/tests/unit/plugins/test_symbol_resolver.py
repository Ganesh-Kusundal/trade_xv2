"""SymbolResolver — (symbol, exchange) → instrument_id string."""

from __future__ import annotations

import pytest

from plugins.brokers.common.symbol_resolver import SymbolNotFoundError, SymbolResolver


def test_resolve_known_symbol() -> None:
    resolver = SymbolResolver()
    resolver.add("RELIANCE", "NSE", "NSE:RELIANCE")
    assert resolver.resolve("RELIANCE", "NSE") == "NSE:RELIANCE"


def test_resolve_unknown_raises() -> None:
    resolver = SymbolResolver()
    with pytest.raises(SymbolNotFoundError):
        resolver.resolve("UNKNOWN", "NSE")


def test_overwrite_mapping() -> None:
    resolver = SymbolResolver()
    resolver.add("RELIANCE", "NSE", "NSE:RELIANCE")
    resolver.add("RELIANCE", "NSE", "NSE:RELIANCE-EQ")
    assert resolver.resolve("RELIANCE", "NSE") == "NSE:RELIANCE-EQ"
