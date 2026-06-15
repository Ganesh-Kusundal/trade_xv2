from __future__ import annotations

import pandas as pd

from analytics import Analytics


def test_scan_facade_api_without_data() -> None:
    result = Analytics().scan()
    assert isinstance(result, dict)
    assert "momentum" in result
    assert "volume" in result


def test_rank_facade_api_without_data() -> None:
    result = Analytics().rank().top_momentum()

    assert result.name == "top_momentum"
    assert result.metrics == {"count": 0}


def test_scan_with_dataframe() -> None:
    data = pd.DataFrame(
        [
            {"symbol": "A", "close": 100, "high": 105, "low": 99, "volume": 5000, "relative_volume": 3.0, "timestamp": "2025-01-01", "open": 100, "oi": 0},
            {"symbol": "B", "close": 90, "high": 92, "low": 89, "volume": 1000, "relative_volume": 0.8, "timestamp": "2025-01-01", "open": 90, "oi": 0},
        ]
    )

    result = Analytics().scan(data, scanner="volume")

    assert hasattr(result, "candidates")
    assert len(result.candidates) > 0
    assert result.candidates[0].symbol == "A"
