"""Regression: DhanInstrumentService.search does not leak wire identifiers."""

from __future__ import annotations

from brokers.dhan.instruments.service import DhanInstrumentService
from brokers.dhan.resolver import SymbolResolver
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS


def test_search_results_exclude_security_id() -> None:
    resolver = SymbolResolver()
    resolver.load_from_rows(SAMPLE_ROWS)
    service = DhanInstrumentService(resolver=resolver)
    results = service.search("RELIANCE", limit=5)
    assert results
    for item in results:
        assert "security_id" not in item
        assert "symbol" in item
        assert "exchange" in item
