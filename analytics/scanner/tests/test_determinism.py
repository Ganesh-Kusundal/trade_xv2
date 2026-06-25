"""Determinism tests for scanner ranking and aggregation."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.scanner.models import Candidate, ScanResult
from analytics.scanner.scanners import (
    BreakoutScanner,
    MomentumScanner,
    RSScanner,
    VolumeScanner,
)


def _universe_with_ties(n_symbols: int = 5, n_bars: int = 30) -> pd.DataFrame:
    """Create a universe where every symbol has identical OHLCV history."""
    frames = []
    for i in range(n_symbols):
        sym = f"SYM{i:02d}"
        timestamps = pd.date_range("2026-01-01", periods=n_bars, freq="min")
        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": sym,
                "open": [100.0 + j * 0.01 for j in range(n_bars)],
                "high": [101.0 + j * 0.01 for j in range(n_bars)],
                "low": [99.0 + j * 0.01 for j in range(n_bars)],
                "close": [100.5 + j * 0.01 for j in range(n_bars)],
                "volume": [1000 + j for j in range(n_bars)],
            }
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


class TestScannerTopNDeterminism:
    @pytest.mark.parametrize(
        "scanner_cls", [MomentumScanner, VolumeScanner, RSScanner, BreakoutScanner]
    )
    def test_repeated_scan_same_order(self, scanner_cls: type) -> None:
        universe = _universe_with_ties(n_symbols=5, n_bars=30)
        scanner = scanner_cls(top_n=3)
        runs = [scanner.scan(universe) for _ in range(10)]
        expected = [c.symbol for c in runs[0].candidates]
        for run in runs[1:]:
            actual = [c.symbol for c in run.candidates]
            assert actual == expected, f"{scanner.name} produced unstable top-N"

    def test_top_n_symbol_tie_breaker(self) -> None:
        universe = _universe_with_ties(n_symbols=5, n_bars=30)
        scanner = MomentumScanner(top_n=3)
        result = scanner.scan(universe)
        symbols = [c.symbol for c in result.candidates]
        assert symbols == sorted(symbols)


class TestScannerDeduplication:
    def test_duplicate_symbol_timestamp_dropped_before_groupby(self) -> None:
        timestamps = pd.date_range("2026-01-01", periods=10, freq="min")
        base = pd.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": "A",
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.0 + i * 0.1 for i in range(10)],
                "volume": [1000] * 10,
            }
        )
        duplicate = base.iloc[[-1]].copy()
        duplicate["close"] = 999.0
        universe = pd.concat([base, duplicate], ignore_index=True)

        scanner = MomentumScanner(top_n=1)
        result = scanner.scan(universe)
        assert len(result.candidates) == 1
        candidate = result.candidates[0]
        assert candidate.score > 50.0


class TestScanResultTop:
    def test_top_uses_symbol_tie_breaker(self) -> None:
        candidates = [
            Candidate(symbol=f"SYM{i:02d}", score=50.0, reasons=[], metrics={}) for i in range(10)
        ]
        result = ScanResult(scanner="test", candidates=candidates)
        top = result.top(n=5)
        assert [c.symbol for c in top] == sorted([c.symbol for c in top])

    def test_top_deterministic_across_runs(self) -> None:
        candidates = [
            Candidate(symbol=f"SYM{i:02d}", score=50.0, reasons=[], metrics={}) for i in range(20)
        ]
        result = ScanResult(scanner="test", candidates=candidates)
        first = [c.symbol for c in result.top(n=10)]
        for _ in range(20):
            assert [c.symbol for c in result.top(n=10)] == first
