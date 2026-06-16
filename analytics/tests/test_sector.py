"""Tests for Sector Analysis module — mapping, rotation, volume, strength."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analytics.sector import (
    RotationAnalyzer,
    RotationPhase,
    RotationResult,
    SectorAnalysisResult,
    SectorAnalyzer,
    SectorMapper,
    SectorStrengthScorer,
    SectorVolumeAnalyzer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate sample OHLCV data with multiple symbols and sectors."""
    np.random.seed(42)
    n_days = 60
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    rows = []
    for sym, sector in [("TCS", "IT"), ("INFY", "IT"), ("RELIANCE", "OilGas"), ("ONGC", "OilGas")]:
        close = 100 + np.cumsum(np.random.randn(n_days) * 2)
        vol = np.random.randint(100000, 500000, n_days).astype(float)
        for i, d in enumerate(dates):
            rows.append({
                "symbol": sym, "sector": sector, "timestamp": d,
                "open": close[i] - 1, "high": close[i] + 2,
                "low": close[i] - 2, "close": close[i], "volume": vol[i],
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sector_returns() -> pd.DataFrame:
    """Generate sector return time series."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "IT": np.random.randn(n) * 0.02,
        "Finance": np.random.randn(n) * 0.015,
        "Pharma": np.random.randn(n) * 0.018,
        "Auto": np.random.randn(n) * 0.022,
        "FMCG": np.random.randn(n) * 0.01,
    }, index=dates)


# ---------------------------------------------------------------------------
# SectorMapper tests
# ---------------------------------------------------------------------------


class TestSectorMapper:
    def test_default_mapping(self) -> None:
        mapper = SectorMapper.default()
        assert mapper.get_sector("TCS") == "IT"
        assert mapper.get_sector("RELIANCE") == "OilGas"
        assert mapper.get_sector("HDFCBANK") == "Finance"
        assert mapper.get_sector("UNKNOWN_STOCK") is None

    def test_get_symbols(self) -> None:
        mapper = SectorMapper.default()
        it_symbols = mapper.get_symbols("IT")
        assert "TCS" in it_symbols
        assert "INFY" in it_symbols
        assert len(it_symbols) >= 10

    def test_sectors_property(self) -> None:
        mapper = SectorMapper.default()
        sectors = mapper.sectors
        assert "IT" in sectors
        assert "Finance" in sectors
        assert "Pharma" in sectors
        assert len(sectors) >= 10

    def test_total_symbols(self) -> None:
        mapper = SectorMapper.default()
        assert mapper.total_symbols >= 100

    def test_sector_counts(self) -> None:
        mapper = SectorMapper.default()
        counts = mapper.sector_counts()
        assert counts["IT"] >= 10
        assert sum(counts.values()) == mapper.total_symbols

    def test_assign_sectors(self) -> None:
        mapper = SectorMapper.default()
        df = pd.DataFrame({"symbol": ["TCS", "RELIANCE", "UNKNOWN"]})
        result = mapper.assign_sectors(df)
        assert result["sector"].tolist() == ["IT", "OilGas", "Unknown"]

    def test_from_dict(self) -> None:
        mapper = SectorMapper.from_dict({"A": "Sec1", "B": "Sec2", "C": "Sec1"})
        assert mapper.get_sector("A") == "Sec1"
        assert len(mapper.get_symbols("Sec1")) == 2

    def test_case_insensitive(self) -> None:
        mapper = SectorMapper.default()
        assert mapper.get_sector("tcs") == "IT"
        assert mapper.get_sector("Reliance") == "OilGas"


# ---------------------------------------------------------------------------
# RotationAnalyzer tests
# ---------------------------------------------------------------------------


class TestRotationAnalyzer:
    def test_analyze_returns_rotation_result(self, sector_returns: pd.DataFrame) -> None:
        analyzer = RotationAnalyzer(lookback=14, momentum_period=10)
        result = analyzer.analyze(sector_returns)
        assert isinstance(result, RotationResult)
        assert len(result.sectors) == 5

    def test_sector_phases(self, sector_returns: pd.DataFrame) -> None:
        result = RotationAnalyzer(lookback=14).analyze(sector_returns)
        for s in result.sectors:
            assert s.phase in (RotationPhase.LEADING, RotationPhase.IMPROVING,
                               RotationPhase.LAGGING, RotationPhase.WEAKENING)

    def test_rotation_regime(self, sector_returns: pd.DataFrame) -> None:
        result = RotationAnalyzer(lookback=14).analyze(sector_returns)
        assert result.rotation_regime in ("Risk-on", "Risk-off", "Rotational", "Neutral")

    def test_breadth_score(self, sector_returns: pd.DataFrame) -> None:
        result = RotationAnalyzer(lookback=14).analyze(sector_returns)
        assert 0 <= result.breadth_score <= 100

    def test_empty_returns(self) -> None:
        result = RotationAnalyzer().analyze(pd.DataFrame())
        assert len(result.sectors) == 0

    def test_sector_scores(self, sector_returns: pd.DataFrame) -> None:
        result = RotationAnalyzer(lookback=14).analyze(sector_returns)
        for s in result.sectors:
            assert 0 <= s.score <= 100

    def test_signals_assigned(self, sector_returns: pd.DataFrame) -> None:
        result = RotationAnalyzer(lookback=14).analyze(sector_returns)
        for s in result.sectors:
            assert s.signal in ("inflow", "outflow", "neutral")


# ---------------------------------------------------------------------------
# SectorVolumeAnalyzer tests
# ---------------------------------------------------------------------------


class TestSectorVolumeAnalyzer:
    def test_analyze_returns_profiles(self, sample_ohlcv: pd.DataFrame) -> None:
        analyzer = SectorVolumeAnalyzer(period=20)
        result = analyzer.analyze(sample_ohlcv)
        assert len(result.profiles) > 0

    def test_volume_profiles_have_metrics(self, sample_ohlcv: pd.DataFrame) -> None:
        result = SectorVolumeAnalyzer(period=20).analyze(sample_ohlcv)
        for p in result.profiles:
            assert p.total_volume > 0
            assert p.avg_daily_volume > 0
            assert 0 <= p.score <= 100

    def test_top_volume_sector(self, sample_ohlcv: pd.DataFrame) -> None:
        result = SectorVolumeAnalyzer(period=20).analyze(sample_ohlcv)
        assert result.top_volume_sector != ""

    def test_volume_concentration(self, sample_ohlcv: pd.DataFrame) -> None:
        result = SectorVolumeAnalyzer(period=20).analyze(sample_ohlcv)
        assert 0 <= result.volume_concentration <= 1

    def test_volume_rotation_signal(self, sample_ohlcv: pd.DataFrame) -> None:
        result = SectorVolumeAnalyzer(period=20).analyze(sample_ohlcv)
        assert result.volume_rotation_signal in ("rotating", "concentrating", "neutral")

    def test_empty_data(self) -> None:
        result = SectorVolumeAnalyzer().analyze(pd.DataFrame())
        assert len(result.profiles) == 0


# ---------------------------------------------------------------------------
# SectorStrengthScorer tests
# ---------------------------------------------------------------------------


class TestSectorStrengthScorer:
    def test_score_returns_results(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {
            "IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"],
            "OilGas": sample_ohlcv[sample_ohlcv["sector"] == "OilGas"],
        }
        scorer = SectorStrengthScorer(period=20)
        result = scorer.score(sector_data)
        assert len(result.sectors) == 2

    def test_sector_ranks(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {
            "IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"],
            "OilGas": sample_ohlcv[sample_ohlcv["sector"] == "OilGas"],
        }
        result = SectorStrengthScorer(period=20).score(sector_data)
        ranks = [s.rank for s in result.sectors]
        assert sorted(ranks) == [1, 2]

    def test_market_strength(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {
            "IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"],
            "OilGas": sample_ohlcv[sample_ohlcv["sector"] == "OilGas"],
        }
        result = SectorStrengthScorer(period=20).score(sector_data)
        assert 0 <= result.market_strength <= 100

    def test_strongest_weakest(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {
            "IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"],
            "OilGas": sample_ohlcv[sample_ohlcv["sector"] == "OilGas"],
        }
        result = SectorStrengthScorer(period=20).score(sector_data)
        assert result.strongest != ""
        assert result.weakest != ""
        assert result.strongest != result.weakest

    def test_signal_classification(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {
            "IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"],
            "OilGas": sample_ohlcv[sample_ohlcv["sector"] == "OilGas"],
        }
        result = SectorStrengthScorer(period=20).score(sector_data)
        for s in result.sectors:
            assert s.signal in ("strong", "neutral", "weak")

    def test_empty_data(self) -> None:
        result = SectorStrengthScorer().score({})
        assert len(result.sectors) == 0


# ---------------------------------------------------------------------------
# SectorAnalyzer integration tests
# ---------------------------------------------------------------------------


class TestSectorAnalyzer:
    def test_full_analysis(self, sample_ohlcv: pd.DataFrame) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        assert isinstance(result, SectorAnalysisResult)
        assert len(result.rotation.sectors) > 0
        assert len(result.volume.profiles) > 0
        assert len(result.strength.sectors) > 0

    def test_to_analysis_result(self, sample_ohlcv: pd.DataFrame) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze(sample_ohlcv)
        ar = analyzer.to_analysis_result(result)
        assert ar.name == "sector_analysis"
        assert "rotation_regime" in ar.metrics
        assert "strongest_sector" in ar.metrics

    def test_rotation_from_returns(self, sector_returns: pd.DataFrame) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze(sector_returns, returns_mode=True)
        assert len(result.rotation.sectors) == 5

    def test_empty_data(self) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze(pd.DataFrame())
        assert len(result.rotation.sectors) == 0

    def test_analyze_rotation_direct(self, sector_returns: pd.DataFrame) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze_rotation(sector_returns)
        assert isinstance(result, RotationResult)

    def test_analyze_volume_direct(self, sample_ohlcv: pd.DataFrame) -> None:
        analyzer = SectorAnalyzer()
        result = analyzer.analyze_volume(sample_ohlcv)
        assert len(result.profiles) > 0

    def test_analyze_strength_direct(self, sample_ohlcv: pd.DataFrame) -> None:
        sector_data = {"IT": sample_ohlcv[sample_ohlcv["sector"] == "IT"]}
        result = SectorAnalyzer().analyze_strength(sector_data)
        assert len(result.sectors) == 1


# ---------------------------------------------------------------------------
# Analytics facade integration
# ---------------------------------------------------------------------------


class TestAnalyticsFacade:
    def test_analytics_has_sector_analyzer(self) -> None:
        from analytics import Analytics
        a = Analytics()
        analyzer = a.sectors()
        assert isinstance(analyzer, SectorAnalyzer)

    def test_analyze_returns_analysis_result(self, sample_ohlcv: pd.DataFrame) -> None:
        from analytics import Analytics
        a = Analytics()
        result = a.sectors(sample_ohlcv)
        assert result.name == "sector_analysis"
