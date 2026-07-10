"""Tests for Scanner ABC and ScannerResult VO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from domain.scanners import Scanner, ScannerResult


def test_scanner_result_frozen():
    r = ScannerResult(symbol="RELIANCE", exchange="NSE", score=0.9)
    with pytest.raises(FrozenInstanceError):
        r.symbol = "TCS"  # type: ignore[misc]


def test_scanner_result_instrument_key():
    r = ScannerResult(symbol="NIFTY", exchange="NSE", score=1.0)
    assert r.instrument_key == "NSE:NIFTY"


def test_scanner_result_default_metadata():
    r = ScannerResult(symbol="X", exchange="BSE", score=0.5)
    assert r.metadata == {}


def test_concrete_scanner():
    class MomentumScanner(Scanner):
        @property
        def name(self) -> str:
            return "momentum"

        def scan(self, symbols, exchange, **kwargs):
            return [
                ScannerResult(symbol=s, exchange=exchange, score=1.0 / (i + 1))
                for i, s in enumerate(symbols)
            ]

    sc = MomentumScanner()
    assert sc.name == "momentum"
    results = sc.scan(["A", "B", "C"], "NSE")
    assert len(results) == 3
    assert results[0].score > results[2].score


def test_scanner_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Scanner()  # type: ignore[abstract]
