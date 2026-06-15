from __future__ import annotations

import pandas as pd

from analytics.ranking.ranking import RankingEngine
from analytics.scanner import VolumeScanner, RSScanner


def test_scanner_and_ranking() -> None:
    data = pd.DataFrame(
        [
            {"symbol": "A", "close": 100, "high": 105, "low": 99, "volume": 5000, "relative_volume": 3.0, "relative_strength": 80, "price_change": 1, "oi_change": 10, "timestamp": "2025-01-01", "open": 100, "oi": 0},
            {"symbol": "B", "close": 90, "high": 92, "low": 89, "volume": 1000, "relative_volume": 0.8, "relative_strength": 30, "price_change": -1, "oi_change": -5, "timestamp": "2025-01-01", "open": 90, "oi": 0},
        ]
    )

    scanner = VolumeScanner()
    result = scanner.scan(data)
    assert len(result.candidates) > 0
    assert result.candidates[0].symbol == "A"

    ranking = RankingEngine()
    ranked = ranking.rank_dataframe(data)

    assert ranked.iloc[0]["symbol"] == "A"
