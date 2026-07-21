"""Single quality validation contract for ingest and catalog checks."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from datalake.quality.validation import ValidationAudit, validate_candles

_SPIKE_GUARD = os.getenv("DATALAKE_SPIKE_GUARD", "").lower() in ("1", "true", "yes")
_SPIKE_PCT = float(os.getenv("DATALAKE_SPIKE_PCT", "0.25") or "0.25")


def _drop_spike_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Optional rate-of-change guard — drops bars whose close jumps > threshold vs prior."""
    if not _SPIKE_GUARD or df.empty or "close" not in df.columns:
        return df, []
    issues: list[str] = []
    closes = pd.to_numeric(df["close"], errors="coerce")
    prev = closes.shift(1)
    pct = ((closes - prev).abs() / prev.abs().replace(0, pd.NA)).fillna(0)
    bad = pct > _SPIKE_PCT
    if bad.any():
        issues.append(f"spike_guard_dropped={int(bad.sum())}")
        df = df.loc[~bad].reset_index(drop=True)
    return df, issues


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

    df, spike_issues = _drop_spike_rows(df)
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
    audit.issues.extend(spike_issues)
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
