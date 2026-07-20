"""Single quality validation contract for ingest and catalog checks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from datalake.quality.validation import ValidationAudit, validate_candles


def validate_at_ingest(
    df: pd.DataFrame,
    *,
    symbol: str = "",
    timeframe: str = "1m",
    drop_invalid: bool = True,
) -> tuple[pd.DataFrame, ValidationAudit]:
    """Hard-fail ingest validation — drops invalid rows by default."""
    total = len(df)
    if df.empty:
        return df, ValidationAudit(
            total_rows=0, valid_rows=0, dropped_rows=0, issues=["empty frame"]
        )

    validated, audit = validate_candles(
        df,
        symbol=symbol,
        drop_invalid=drop_invalid,
        timeframe=timeframe,
        return_audit=True,
    )
    audit.total_rows = total
    audit.valid_rows = len(validated)
    audit.dropped_rows = total - len(validated)
    return validated, audit


def validate_parquet_file(path: str | Path, symbol: str = "") -> dict:
    """Validate a Parquet file — invalid rows count toward invalid_rows."""
    df = pd.read_parquet(path)
    if df.empty:
        return {"total_rows": 0, "valid_rows": 0, "invalid_rows": 0, "issues": ["empty file"]}

    _, audit = validate_at_ingest(df, symbol=symbol, drop_invalid=True)
    return {
        "total_rows": audit.total_rows,
        "valid_rows": audit.valid_rows,
        "invalid_rows": audit.dropped_rows,
        "issues": audit.issues,
    }


def completeness_pct(actual: int, expected: int) -> float:
    """Completeness ratio; zero expected gaps → 100%."""
    if expected <= 0:
        return 100.0
    return min(100.0, (actual / expected) * 100.0)
