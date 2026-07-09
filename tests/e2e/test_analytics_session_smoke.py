"""AN-010: Session → instruments → history → analytics.scanner smoke.

Proves the product path into the **live / event-capable** scanner
(``analytics.scanner``) without live broker data and without merging
the dual scanners (``datalake.scanner`` remains research-only).

Path under test::

    tradex.connect("paper")
      → session.universe.equity(symbol)
      → instrument.history(...).to_dataframe()
      → MomentumScanner.scan(universe_df)

No gateway imports; paper synthetic history only.
"""

from __future__ import annotations

import pandas as pd
import pytest

import tradex
from analytics.scanner import MomentumScanner
from analytics.scanner.models import ScanResult
from domain.candles.historical import HistoricalSeries

pytestmark = pytest.mark.e2e

# Small fixed universe — paper history needs no network.
_SESSION_SYMBOLS = ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")


def _universe_from_session(session, symbols: tuple[str, ...] = _SESSION_SYMBOLS) -> pd.DataFrame:
    """Build a multi-symbol OHLCV frame from session instruments + history."""
    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        inst = session.universe.equity(symbol)
        series = inst.history(timeframe="1D", days=60)
        assert isinstance(series, HistoricalSeries)
        assert series.bar_count >= 50, f"{symbol}: expected enough bars for features"
        df = series.to_dataframe()
        assert not df.empty
        assert "symbol" in df.columns
        assert set(df["symbol"].unique()) == {symbol}
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_session_instruments_feed_analytics_scanner() -> None:
    """AN-010: paper session symbols + history exercise analytics.scanner."""
    session = tradex.connect("paper")
    try:
        universe = _universe_from_session(session)
        assert universe["symbol"].nunique() == len(_SESSION_SYMBOLS)
        for col in ("timestamp", "open", "high", "low", "close", "volume", "symbol"):
            assert col in universe.columns

        result = MomentumScanner(top_n=3).scan(universe)

        assert isinstance(result, ScanResult)
        assert result.scanner == "momentum"
        assert result.universe_size > 0
        assert len(result.candidates) > 0
        assert len(result.candidates) <= 3
        # Symbols returned must come from the session-derived universe
        allowed = set(_SESSION_SYMBOLS)
        for candidate in result.candidates:
            assert candidate.symbol in allowed
            assert 0 <= candidate.score <= 100
    finally:
        session.close()


def test_analytics_scanner_import_path_not_datalake() -> None:
    """Guard: live path uses analytics.scanner; do not merge dual scanners."""
    import analytics.scanner as live_scanner
    import analytics.scanner.scanners as live_scanners

    assert hasattr(live_scanner, "MomentumScanner")
    assert hasattr(live_scanners, "MomentumScanner")
    # Research SQL path stays separate (importable, not wired here)
    import analytics.scanner.rules  # noqa: F401
