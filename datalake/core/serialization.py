"""Serialization utilities for converting DataFrames to JSON-serializable dicts."""

from __future__ import annotations

import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of JSON-serializable dicts.

    Handles:
    - Timestamps → ISO format strings
    - NumPy scalars → Python primitives
    - NaN → None

    Usage:
        records = df_to_records(df)
        return {"count": len(records), "data": records}
    """
    if df.empty:
        return []

    records = df.to_dict(orient="records")
    return _sanitize_records(records)


def _sanitize_records(records: list[dict]) -> list[dict]:
    """Sanitize a list of dicts for JSON serialization."""
    for r in records:
        for k, v in r.items():
            if v is None:
                continue
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
            elif hasattr(v, "item"):
                r[k] = v.item()
            elif isinstance(v, float) and pd.isna(v):
                r[k] = None
    return records
