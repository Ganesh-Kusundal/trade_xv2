"""Momentum PoC — Label Generation (≥5% return target)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import CANDLES_DIR, POC_DATA, LABELS_PATH, MIN_RETURN_PCT
import duckdb

def main() -> None:
    POC_DATA.mkdir(parents=True, exist_ok=True)
    glob_pattern = str(CANDLES_DIR / "symbol=*" / "data.parquet")
    print("Computing labels via DuckDB SQL...")
    conn = duckdb.connect(":memory:")

    df = conn.execute(f"""
        WITH base AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) AS date,
                CAST(timestamp AS TIME) AS tod,
                close
            FROM read_parquet('{glob_pattern}', hive_partitioning=true)
        ),
        morning AS (
            SELECT symbol, date, LAST_VALUE(close) OVER w AS close_0945
            FROM base WHERE tod <= TIME '09:45'
            WINDOW w AS (PARTITION BY symbol, date ORDER BY tod
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ),
        afternoon AS (
            SELECT symbol, date, LAST_VALUE(close) OVER w AS close_1515
            FROM base WHERE tod >= TIME '15:00'
            WINDOW w AS (PARTITION BY symbol, date ORDER BY tod
                         ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ),
        morning_dedup AS (SELECT DISTINCT * FROM morning),
        afternoon_dedup AS (SELECT DISTINCT * FROM afternoon)
        SELECT
            m.symbol, m.date, m.close_0945, a.close_1515,
            (a.close_1515 - m.close_0945) / NULLIF(m.close_0945, 0) * 100 AS return_pct,
            CASE WHEN (a.close_1515 - m.close_0945) / NULLIF(m.close_0945, 0) * 100 >= {MIN_RETURN_PCT}
                 THEN 1 ELSE 0 END AS label
        FROM morning_dedup m
        JOIN afternoon_dedup a ON m.symbol = a.symbol AND m.date = a.date
        WHERE m.close_0945 > 0
        ORDER BY m.symbol, m.date
    """).fetchdf()
    conn.close()

    df.to_parquet(str(LABELS_PATH), index=False)
    n_pos = df["label"].sum()
    print(f"\n{'='*50}")
    print(f"Labels: {len(df):,} rows")
    print(f"Positive (≥{MIN_RETURN_PCT}% return): {n_pos:,} ({df['label'].mean()*100:.1f}%)")
    print(f"Date range: {df['date'].min()} → {df['date'].max()}")
    print(f"Saved: {LABELS_PATH}")

if __name__ == "__main__":
    main()
