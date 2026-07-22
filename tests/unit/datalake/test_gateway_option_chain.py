"""DataLakeGateway.option_chain reads options/candles parquet."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from datalake.gateway import DataLakeGateway


def test_option_chain_reads_candles_partition(tmp_path: Path) -> None:
    root = tmp_path / "lake"
    part = (
        root
        / "options"
        / "candles"
        / "underlying=NIFTY"
        / "expiry_kind=WEEK"
        / "expiry_code=1"
    )
    part.mkdir(parents=True)
    df = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-03-02 09:15:00"),
                "symbol": "NIFTY_WEEK_1_0_CALL",
                "underlying": "NIFTY",
                "exchange": "NSE",
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 102.0,
                "volume": 1000,
                "oi": 5000,
                "iv": 15.0,
                "spot": 23600.0,
                "strike": 23600.0,
                "strike_offset": 0,
                "option_type": "CALL",
                "expiry_kind": "WEEK",
                "expiry_code": 1,
                "interval_min": 5,
                "expiry_date": "2026-03-05",
            },
            {
                "timestamp": pd.Timestamp("2026-03-02 09:15:00"),
                "symbol": "NIFTY_WEEK_1_0_PUT",
                "underlying": "NIFTY",
                "exchange": "NSE",
                "open": 90.0,
                "high": 95.0,
                "low": 85.0,
                "close": 92.0,
                "volume": 800,
                "oi": 4000,
                "iv": 16.0,
                "spot": 23600.0,
                "strike": 23600.0,
                "strike_offset": 0,
                "option_type": "PUT",
                "expiry_kind": "WEEK",
                "expiry_code": 1,
                "interval_min": 5,
                "expiry_date": "2026-03-05",
            },
        ]
    )
    df.to_parquet(part / "data.parquet", index=False)

    chain = DataLakeGateway(root=str(root)).option_chain("NIFTY")
    assert len(chain["calls"]) == 1
    assert len(chain["puts"]) == 1
    assert chain["expiry"] == "2026-03-05"
