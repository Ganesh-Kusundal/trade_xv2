"""Tests for FeaturePipeline and scanner framework."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics.pipeline import (
    ATR,
    EMA,
    MACD,
    ROC,
    RSI,
    SMA,
    VWAP,
    BollingerBands,
    FeaturePipeline,
    Gap,
    HistoricalVolatility,
    Momentum,
    RelativeVolume,
    SwingHighLow,
    Trend,
)
from analytics.scanner import (
    BreakoutScanner,
    Candidate,
    MomentumScanner,
    RSScanner,
    Scanner,
    ScanResult,
    VolumeScanner,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Generate sample OHLCV data."""
    import numpy as np

    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": close + np.random.randn(n),
            "high": close + abs(np.random.randn(n) * 2),
            "low": close - abs(np.random.randn(n) * 2),
            "close": close,
            "volume": np.random.randint(100000, 1000000, n),
        }
    )


@pytest.fixture
def universe_df() -> pd.DataFrame:
    """Generate sample universe with multiple symbols."""
    import numpy as np

    np.random.seed(42)
    symbols = ["RELIANCE", "TCS", "HDFCBANK"]
    rows = []
    for sym in symbols:
        n = 60
        dates = pd.date_range("2026-01-01", periods=n, freq="D")
        close = 100 + np.cumsum(np.random.randn(n) * 2) + hash(sym) % 100
        df = pd.DataFrame(
            {
                "timestamp": dates,
                "open": close + np.random.randn(n),
                "high": close + abs(np.random.randn(n) * 2),
                "low": close - abs(np.random.randn(n) * 2),
                "close": close,
                "volume": np.random.randint(100000, 1000000, n),
                "symbol": sym,
            }
        )
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# FeaturePipeline Tests
# ---------------------------------------------------------------------------


class TestFeaturePipeline:
    def test_empty_pipeline(self, sample_df: pd.DataFrame) -> None:
        pipeline = FeaturePipeline()
        result = pipeline.run(sample_df)
        assert len(result) == len(sample_df)
        assert list(result.columns) == list(sample_df.columns)

    def test_single_feature(self, sample_df: pd.DataFrame) -> None:
        pipeline = FeaturePipeline().add(RSI(period=14))
        result = pipeline.run(sample_df)
        assert "rsi" in result.columns
        assert result["rsi"].notna().sum() > 0

    def test_chaining(self, sample_df: pd.DataFrame) -> None:
        pipeline = FeaturePipeline().add(ATR(period=14)).add(VWAP()).add(RSI(period=14))
        result = pipeline.run(sample_df)
        assert "atr" in result.columns
        assert "vwap" in result.columns
        assert "rsi" in result.columns

    def test_feature_names(self) -> None:
        pipeline = FeaturePipeline().add(ATR(period=14)).add(RSI(period=14)).add(VWAP())
        assert pipeline.feature_names() == ["atr", "rsi", "vwap"]

    def test_len(self) -> None:
        pipeline = FeaturePipeline().add(ATR(14)).add(RSI(14))
        assert len(pipeline) == 2

    def test_empty_df(self) -> None:
        pipeline = FeaturePipeline().add(RSI(14))
        result = pipeline.run(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Individual Feature Tests
# ---------------------------------------------------------------------------


class TestATR:
    def test_computes_atr(self, sample_df: pd.DataFrame) -> None:
        feature = ATR(period=14)
        result = feature.compute(sample_df)
        assert "atr" in result.columns
        assert result["atr"].iloc[:13].isna().all()
        assert result["atr"].iloc[14:].notna().all()

    def test_atr_positive(self, sample_df: pd.DataFrame) -> None:
        feature = ATR(period=14)
        result = feature.compute(sample_df)
        valid = result["atr"].dropna()
        assert (valid >= 0).all()


class TestVWAP:
    def test_computes_vwap(self, sample_df: pd.DataFrame) -> None:
        feature = VWAP()
        result = feature.compute(sample_df)
        assert "vwap" in result.columns
        assert result["vwap"].notna().all()


class TestRSI:
    def test_computes_rsi(self, sample_df: pd.DataFrame) -> None:
        feature = RSI(period=14)
        result = feature.compute(sample_df)
        assert "rsi" in result.columns
        valid = result["rsi"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestSMA:
    def test_computes_sma(self, sample_df: pd.DataFrame) -> None:
        feature = SMA(period=20)
        result = feature.compute(sample_df)
        assert "sma" in result.columns
        assert result["sma"].notna().all()


class TestEMA:
    def test_computes_ema(self, sample_df: pd.DataFrame) -> None:
        feature = EMA(period=20)
        result = feature.compute(sample_df)
        assert "ema" in result.columns
        assert result["ema"].notna().all()


class TestBollingerBands:
    def test_computes_bands(self, sample_df: pd.DataFrame) -> None:
        feature = BollingerBands(period=20)
        result = feature.compute(sample_df)
        assert "bb_upper" in result.columns
        assert "bb_lower" in result.columns
        assert "bb_pct_b" in result.columns
        assert "bb_bandwidth" in result.columns


class TestMACD:
    def test_computes_macd(self, sample_df: pd.DataFrame) -> None:
        feature = MACD()
        result = feature.compute(sample_df)
        assert "macd_line" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_histogram" in result.columns


class TestRelativeVolume:
    def test_computes_relative_volume(self, sample_df: pd.DataFrame) -> None:
        feature = RelativeVolume(period=20)
        result = feature.compute(sample_df)
        assert "relative_volume" in result.columns
        assert result["relative_volume"].notna().all()


class TestROC:
    def test_computes_roc(self, sample_df: pd.DataFrame) -> None:
        feature = ROC(period=5)
        result = feature.compute(sample_df)
        assert "roc" in result.columns
        assert result["roc"].notna().all()


class TestMomentum:
    def test_computes_momentum(self, sample_df: pd.DataFrame) -> None:
        feature = Momentum(period=5)
        result = feature.compute(sample_df)
        assert "momentum" in result.columns
        assert result["momentum"].notna().all()


class TestTrend:
    def test_computes_trend(self, sample_df: pd.DataFrame) -> None:
        feature = Trend()
        result = feature.compute(sample_df)
        assert "trend" in result.columns
        assert set(result["trend"].unique()) <= {"up", "down", "neutral"}


class TestGap:
    def test_computes_gap(self, sample_df: pd.DataFrame) -> None:
        feature = Gap()
        result = feature.compute(sample_df)
        assert "gap_pct" in result.columns
        assert result["gap_pct"].iloc[0] != result["gap_pct"].iloc[0]  # NaN check


class TestSwingHighLow:
    def test_computes_swings(self, sample_df: pd.DataFrame) -> None:
        feature = SwingHighLow(lookback=5)
        result = feature.compute(sample_df)
        assert "swing_high" in result.columns
        assert "swing_low" in result.columns
        assert "last_swing_high" in result.columns
        assert "last_swing_low" in result.columns
        assert result["swing_high"].dtype == bool
        assert result["swing_low"].dtype == bool

    def test_no_lookahead_on_truncated_series(self, sample_df: pd.DataFrame) -> None:
        """Confirmed swings at bar i must not change when future bars are added."""
        feature = SwingHighLow(lookback=5)
        full = feature.compute(sample_df.copy())
        cut = len(sample_df) // 2
        partial = feature.compute(sample_df.iloc[:cut].copy())
        check_idx = cut - 6
        if check_idx < 0:
            pytest.skip("sample too short")
        assert full["last_swing_high"].iloc[check_idx] == pytest.approx(
            partial["last_swing_high"].iloc[check_idx]
        )
        assert full["last_swing_low"].iloc[check_idx] == pytest.approx(
            partial["last_swing_low"].iloc[check_idx]
        )


class TestHistoricalVolatility:
    def test_computes_volatility(self, sample_df: pd.DataFrame) -> None:
        feature = HistoricalVolatility(period=20)
        result = feature.compute(sample_df)
        assert "hist_volatility" in result.columns


# ---------------------------------------------------------------------------
# Candidate and ScanResult Tests
# ---------------------------------------------------------------------------


class TestCandidate:
    def test_valid_candidate(self) -> None:
        c = Candidate(symbol="RELIANCE", score=85.0, reasons=["High RS"])
        assert c.symbol == "RELIANCE"
        assert c.score == 85.0

    def test_invalid_score(self) -> None:
        with pytest.raises(ValueError, match="Score must be 0-100"):
            Candidate(symbol="RELIANCE", score=150.0)

    def test_negative_score(self) -> None:
        with pytest.raises(ValueError, match="Score must be 0-100"):
            Candidate(symbol="RELIANCE", score=-10.0)


class TestScanResult:
    def test_empty_result(self) -> None:
        result = ScanResult(scanner="test")
        assert result.count == 0
        assert result.top(5) == []

    def test_top_n(self) -> None:
        candidates = [
            Candidate(symbol="A", score=90),
            Candidate(symbol="B", score=80),
            Candidate(symbol="C", score=70),
        ]
        result = ScanResult(scanner="test", candidates=candidates)
        assert result.count == 3
        assert len(result.top(2)) == 2
        assert result.top(2)[0].symbol == "A"

    def test_to_dataframe(self) -> None:
        candidates = [
            Candidate(symbol="A", score=90, reasons=["RS"]),
            Candidate(symbol="B", score=80),
        ]
        result = ScanResult(scanner="test", candidates=candidates)
        df = result.to_dataframe()
        assert len(df) == 2
        assert "symbol" in df.columns
        assert "score" in df.columns


# ---------------------------------------------------------------------------
# Scanner Tests
# ---------------------------------------------------------------------------


class TestMomentumScanner:
    def test_scan_returns_result(self, universe_df: pd.DataFrame) -> None:
        scanner = MomentumScanner()
        result = scanner.scan(universe_df)
        assert isinstance(result, ScanResult)
        assert result.scanner == "momentum"
        assert result.count == 3

    def test_scan_empty_universe(self) -> None:
        scanner = MomentumScanner()
        result = scanner.scan(pd.DataFrame())
        assert result.count == 0


class TestVolumeScanner:
    def test_scan_returns_result(self, universe_df: pd.DataFrame) -> None:
        scanner = VolumeScanner()
        result = scanner.scan(universe_df)
        assert isinstance(result, ScanResult)
        assert result.scanner == "volume"
        assert result.count == 3


class TestRSScanner:
    def test_scan_returns_result(self, universe_df: pd.DataFrame) -> None:
        scanner = RSScanner()
        result = scanner.scan(universe_df)
        assert isinstance(result, ScanResult)
        assert result.scanner == "rs"
        assert result.count == 3


class TestBreakoutScanner:
    def test_scan_returns_result(self, universe_df: pd.DataFrame) -> None:
        scanner = BreakoutScanner()
        result = scanner.scan(universe_df)
        assert isinstance(result, ScanResult)
        assert result.scanner == "breakout"
        assert result.count == 3


class TestScannerProtocol:
    def test_momentum_is_scanner(self) -> None:
        assert isinstance(MomentumScanner(), Scanner)

    def test_volume_is_scanner(self) -> None:
        assert isinstance(VolumeScanner(), Scanner)

    def test_rs_is_scanner(self) -> None:
        assert isinstance(RSScanner(), Scanner)

    def test_breakout_is_scanner(self) -> None:
        assert isinstance(BreakoutScanner(), Scanner)
