"""Universe-level data quality checks — cross-symbol consistency.

Extends per-symbol DataQualityEngine with universe-wide checks:
- Sector correlation divergence
- Index ETF tracking error
- Cross-symbol volume anomalies
- Stale data detection across universe
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from datalake.quality import DataQualityEngine

logger = logging.getLogger(__name__)


@dataclass
class UniverseQualityReport:
    universe: str = ""
    symbol_count: int = 0
    symbols_with_data: int = 0
    symbols_missing: list[str] = field(default_factory=list)
    stale_symbols: list[str] = field(default_factory=list)
    sector_divergences: list[dict] = field(default_factory=list)
    volume_anomalies: list[dict] = field(default_factory=list)
    overall_status: str = "OK"
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"=== Universe Quality: {self.universe} ===",
            f"Status: {self.overall_status}",
            f"Symbols: {self.symbols_with_data}/{self.symbol_count} with data",
            f"Missing: {len(self.symbols_missing)}",
            f"Stale: {len(self.stale_symbols)}",
            f"Sector divergences: {len(self.sector_divergences)}",
            f"Volume anomalies: {len(self.volume_anomalies)}",
        ]
        if self.issues:
            lines.append("\nIssues:")
            for issue in self.issues[:20]:
                lines.append(f"  - {issue}")
        return "\n".join(lines)


class UniverseQualityEngine:
    """Cross-symbol quality checks for an entire universe."""

    def __init__(self, root: str = "market_data", catalog=None) -> None:
        self._root = Path(root)
        self._catalog = catalog
        self._symbol_quality = DataQualityEngine(root, catalog)

    def check(
        self,
        universe: str = "NIFTY500",
        timeframe: str = "1m",
        max_stale_days: int = 3,
        sector_mapping: dict[str, str] | None = None,
        symbols: list[str] | None = None,
    ) -> UniverseQualityReport:
        """Run full universe quality check.

        Args:
            universe: Universe name (NIFTY50, NIFTY100, NIFTY200, NIFTY500).
            timeframe: Candle timeframe.
            max_stale_days: Max days before a symbol is considered stale.
            sector_mapping: Optional {symbol: sector} mapping.
            symbols: Optional explicit symbol list (bypasses load_universe).
        """
        report = UniverseQualityReport(universe=universe)
        if symbols is None:
            from datalake.schema import load_universe
            symbols = load_universe(universe, catalog=self._catalog)
        report.symbol_count = len(symbols)

        if not symbols:
            report.overall_status = "EMPTY"
            report.issues.append("No symbols found in universe")
            return report

        symbol_data: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            parquet_path = (
                self._root
                / "equities"
                / "candles"
                / f"timeframe={timeframe}"
                / f"symbol={symbol}"
                / "data.parquet"
            )
            if not parquet_path.exists():
                report.symbols_missing.append(symbol)
                continue

            try:
                df = pd.read_parquet(parquet_path)
                if df.empty:
                    report.symbols_missing.append(symbol)
                    continue
                symbol_data[symbol] = df
                report.symbols_with_data += 1
            except Exception as exc:
                logger.warning("Failed to read %s: %s", symbol, exc)
                report.symbols_missing.append(symbol)

        from datetime import timedelta

        max_date_map: dict[str, pd.Timestamp] = {}
        for symbol, df in symbol_data.items():
            if "timestamp" in df.columns:
                ts = pd.to_datetime(df["timestamp"])
                max_date_map[symbol] = ts.max()

        if max_date_map:
            latest_global = max(max_date_map.values())
            cutoff = latest_global - timedelta(days=max_stale_days)
            for symbol, last_ts in max_date_map.items():
                if last_ts < cutoff:
                    report.stale_symbols.append(symbol)

        if sector_mapping:
            report.sector_divergences = self._check_sector_divergence(
                symbol_data, sector_mapping
            )

        report.volume_anomalies = self._check_volume_anomalies(symbol_data)

        if report.symbols_missing:
            report.issues.append(
                f"{len(report.symbols_missing)} symbols missing data"
            )
        if report.stale_symbols:
            report.issues.append(
                f"{len(report.stale_symbols)} symbols stale (>{max_stale_days} days)"
            )
        if report.sector_divergences:
            report.issues.append(
                f"{len(report.sector_divergences)} sector divergences detected"
            )
        if report.volume_anomalies:
            report.issues.append(
                f"{len(report.volume_anomalies)} volume anomalies detected"
            )

        if report.issues:
            report.overall_status = "WARNING"
        if len(report.symbols_missing) > report.symbol_count * 0.1:
            report.overall_status = "CRITICAL"

        return report

    def _check_sector_divergence(
        self,
        symbol_data: dict[str, pd.DataFrame],
        sector_mapping: dict[str, str],
        lookback_days: int = 30,
        threshold_pct: float = 10.0,
    ) -> list[dict]:
        """Check if any sector's average return diverges excessively from the market.

        Args:
            symbol_data: {symbol: DataFrame} with OHLCV data.
            sector_mapping: {symbol: sector} mapping.
            lookback_days: Days of return to compare.
            threshold_pct: Divergence threshold in percentage points.
        """
        from datetime import timedelta

        returns_by_sector: dict[str, list[float]] = {}
        all_returns: list[float] = []

        for symbol, df in symbol_data.items():
            if symbol not in sector_mapping:
                continue
            if "close" not in df.columns or "timestamp" not in df.columns:
                continue

            ts = pd.to_datetime(df["timestamp"])
            cutoff = ts.max() - timedelta(days=lookback_days)
            recent = df[ts >= cutoff].copy()
            if len(recent) < 2:
                continue

            sector = sector_mapping[symbol]
            ret = (recent["close"].iloc[-1] / recent["close"].iloc[0] - 1) * 100
            returns_by_sector.setdefault(sector, []).append(ret)
            all_returns.append(ret)

        if not all_returns:
            return []

        market_avg = sum(all_returns) / len(all_returns)
        divergences = []

        for sector, rets in returns_by_sector.items():
            sector_avg = sum(rets) / len(rets)
            divergence = sector_avg - market_avg
            if abs(divergence) > threshold_pct:
                divergences.append({
                    "sector": sector,
                    "sector_avg_return_pct": round(sector_avg, 2),
                    "market_avg_return_pct": round(market_avg, 2),
                    "divergence_pct": round(divergence, 2),
                    "symbol_count": len(rets),
                })

        return sorted(divergences, key=lambda x: abs(x["divergence_pct"]), reverse=True)

    def _check_volume_anomalies(
        self,
        symbol_data: dict[str, pd.DataFrame],
        lookback_days: int = 30,
        z_threshold: float = 3.0,
    ) -> list[dict]:
        """Detect symbols with volume z-scores above threshold (recent vs historical).

        Args:
            symbol_data: {symbol: DataFrame} with OHLCV data.
            lookback_days: Historical window for baseline.
            z_threshold: Z-score threshold for anomaly detection.
        """
        from datetime import timedelta

        anomalies = []

        for symbol, df in symbol_data.items():
            if "volume" not in df.columns or "timestamp" not in df.columns:
                continue

            ts = pd.to_datetime(df["timestamp"])
            cutoff = ts.max() - timedelta(days=lookback_days)
            historical = df[ts < cutoff]
            recent = df[ts >= cutoff]

            if len(historical) < 30 or len(recent) < 5:
                continue

            hist_mean = historical["volume"].mean()
            hist_std = historical["volume"].std()

            recent_avg = recent["volume"].mean()

            if hist_std > 0:
                z_score = (recent_avg - hist_mean) / hist_std
            elif hist_mean > 0 and recent_avg > hist_mean * 2:
                z_score = z_threshold + 1.0
            else:
                continue

            if abs(z_score) > z_threshold:
                anomalies.append({
                    "symbol": symbol,
                    "recent_avg_volume": int(recent_avg),
                    "historical_avg_volume": int(hist_mean),
                    "z_score": round(z_score, 2),
                    "direction": "high" if z_score > 0 else "low",
                })

        return sorted(anomalies, key=lambda x: abs(x["z_score"]), reverse=True)
