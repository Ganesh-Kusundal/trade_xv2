"""Momentum PoC — Data Audit (DuckDB batch version).

Uses DuckDB read_parquet() to batch-query all symbols efficiently.
Handles schema inconsistencies (dictionary vs string) automatically.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CANDLES_DIR, POC_DATA, AUDIT_PATH

import duckdb


def main() -> None:
    POC_DATA.mkdir(parents=True, exist_ok=True)

    glob_pattern = str(CANDLES_DIR / "symbol=*" / "data.parquet")
    print(f"Scanning: {glob_pattern}")

    conn = duckdb.connect(":memory:")

    # Batch query: read ALL parquet files at once via DuckDB glob
    # DuckDB auto-handles schema mismatches (dictionary vs string)
    print("Running batch audit query...")
    df = conn.execute(f"""
        SELECT
            symbol,
            COUNT(*)                                    AS rows,
            MIN(timestamp)                              AS min_ts,
            MAX(timestamp)                              AS max_ts,
            MIN(close)                                  AS min_close,
            MAX(close)                                  AS max_close,
            AVG(volume)                                 AS avg_vol,
            SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) AS zero_vol,
            SUM(CASE WHEN close  = 0 THEN 1 ELSE 0 END) AS zero_close
        FROM read_parquet('{glob_pattern}', hive_partitioning=true)
        GROUP BY symbol
        ORDER BY symbol
    """).fetchdf()

    conn.close()

    # Build report
    results = []
    for _, row in df.iterrows():
        results.append({
            "symbol": row["symbol"],
            "exists": True,
            "rows": int(row["rows"]),
            "min_ts": str(row["min_ts"]),
            "max_ts": str(row["max_ts"]),
            "min_close": float(row["min_close"]),
            "max_close": float(row["max_close"]),
            "avg_volume": int(row["avg_vol"]) if row["avg_vol"] else 0,
            "zero_volume_bars": int(row["zero_vol"]),
            "zero_close_bars": int(row["zero_close"]),
        })

    report = {
        "audit_ts": datetime.now().isoformat(),
        "total_symbols": len(results),
        "valid": len(results),
        "total_bars": int(df["rows"].sum()),
        "date_range": f"{df['min_ts'].min()} → {df['max_ts'].max()}",
        "details": results,
    }

    AUDIT_PATH.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n{'='*50}")
    print(f"Audit complete: {len(results)} symbols, {report['total_bars']:,} total bars")
    print(f"Date range: {report['date_range']}")
    print(f"Report: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
