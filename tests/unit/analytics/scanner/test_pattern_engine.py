"""PatternEngine, PatternRegistry, PatternScanner, PatternStrategy guarantees.

File-per-guarantee: determinism, registry contract, scanner ranking, and
strategy signal direction are each isolated.
"""

from __future__ import annotations

import pandas as pd

from analytics.scanner.patterns import (
    PatternEngine,
    PatternHit,
    PatternRegistry,
    PatternResult,
    PatternScanner,
    PatternStrategy,
)
from analytics.strategy.models import SignalType
from domain.indicators.patterns import PatternColumns


def _universe() -> pd.DataFrame:
    frames = []
    # SYM00: bars 0-7 gentle uptrend, bar 8 bearish, bar 9 bullish engulfing.
    sym00 = []
    ts = pd.date_range("2026-01-01", periods=10, freq="min")
    for i in range(8):
        sym00.append(
            {
                "open": 100.0 + i * 0.1,
                "high": 101.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": 100.5 + i * 0.1,
                "volume": 1000,
            }
        )
    # bar 8: bearish (open > close)
    sym00.append({"open": 102.0, "high": 102.5, "low": 100.0, "close": 100.5, "volume": 1000})
    # bar 9: bullish engulfing (open <= prev close, close >= prev open)
    sym00.append({"open": 99.5, "high": 103.0, "low": 99.0, "close": 102.5, "volume": 1000})
    frames.append(
        pd.DataFrame(
            {
                "timestamp": ts,
                "symbol": "SYM00",
                "open": [b["open"] for b in sym00],
                "high": [b["high"] for b in sym00],
                "low": [b["low"] for b in sym00],
                "close": [b["close"] for b in sym00],
                "volume": [b["volume"] for b in sym00],
            }
        )
    )
    # SYM01 is a flat, pattern-free series.
    frames.append(
        pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=10, freq="min"),
                "symbol": "SYM01",
                "open": [100.0 + i * 0.05 for i in range(10)],
                "high": [101.0 + i * 0.05 for i in range(10)],
                "low": [99.0 + i * 0.05 for i in range(10)],
                "close": [100.5 + i * 0.05 for i in range(10)],
                "volume": [1000] * 10,
            }
        )
    )
    return pd.concat(frames, ignore_index=True)


def test_engine_runs_deterministically() -> None:
    engine = PatternEngine()
    universe = _universe()
    a = engine.run(universe)
    b = engine.run(universe)
    pd.testing.assert_frame_equal(a.to_dataframe(), b.to_dataframe())
    assert a.universe_size == 2


def test_engine_emits_bullish_hit_for_engulfing() -> None:
    engine = PatternEngine()
    result = engine.run(_universe())
    assert isinstance(result, PatternResult)
    hits = [h for h in result.hits if h.symbol == "SYM00"]
    assert any(h.pattern == PatternColumns.ENGULFING_BULL for h in hits)
    assert all(isinstance(h, PatternHit) for h in hits)


def test_registry_contract() -> None:
    PatternRegistry.register("candlestick", PatternEngine)
    assert "candlestick" in PatternRegistry.list()
    assert PatternRegistry.get("candlestick") is PatternEngine
    assert isinstance(PatternRegistry.create("candlestick"), PatternEngine)
    PatternRegistry.clear()
    assert "candlestick" not in PatternRegistry.list()


def test_pattern_scanner_ranks_pattern_symbol_higher() -> None:
    scanner = PatternScanner(top_n=2)
    result = scanner.scan(_universe())
    assert result.count >= 1
    # SYM00 (bullish engulfing) should outrank the flat SYM01.
    top = result.top(n=2)
    assert top[0].symbol == "SYM00"
    assert top[0].score > 50.0


def test_pattern_strategy_signals_buy_on_bullish_pattern() -> None:
    from analytics.scanner.models import Candidate

    features = PatternEngine().pipeline.run(_universe())
    sym00 = features[features["symbol"] == "SYM00"].sort_values("timestamp")
    signal = PatternStrategy().evaluate(Candidate(symbol="SYM00", score=50.0), sym00)
    assert signal.signal_type == SignalType.BUY
    assert signal.confidence > 0.0
