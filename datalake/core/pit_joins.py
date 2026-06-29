from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import duckdb
import pandas as pd


@dataclass
class PitQueryConfig:
    as_of_column: str = "event_time"
    published_at_column: str = "published_at"
    strict: bool = True
    max_lookback_window: str | None = None


_LOOKAHEAD_PATTERNS: list[re.Pattern] = [
    re.compile(r"LEAD\s*\(", re.IGNORECASE),
    re.compile(r"UNBOUNDED\s+FOLLOWING", re.IGNORECASE),
    re.compile(r"ROWS\s+BETWEEN.*?FOLLOWING", re.IGNORECASE),
    re.compile(r"RANGE\s+BETWEEN.*?FOLLOWING", re.IGNORECASE),
]


def validate_no_lookahead(sql: str) -> list[str]:
    warnings: list[str] = []
    for pattern in _LOOKAHEAD_PATTERNS:
        for match in pattern.finditer(sql):
            col = match.start()
            line_num = sql[:col].count("\n") + 1
            warnings.append(
                f"Line {line_num}: possible look-ahead pattern found — "
                f"{match.group().strip()!r} (column {col})"
            )
    return warnings


def _get_column_names(conn: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"DESCRIBE {table}").fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _require_columns(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    required: list[str],
    table_label: str,
) -> None:
    existing = _get_column_names(conn, table)
    if not existing:
        return
    missing = [c for c in required if c not in existing]
    if missing:
        raise ValueError(
            f"{table_label} table '{table}' is missing required temporal "
            f"column(s): {missing}. Available columns: {sorted(existing)}"
        )


def as_of_join(
    conn: duckdb.DuckDBPyConnection,
    left_table: str,
    right_table: str,
    on: list[str],
    as_of_column: str = "event_time",
    right_published_at: str = "published_at",
    select_left: list[str] | None = None,
    select_right: list[str] | None = None,
    left_alias: str = "l",
    right_alias: str = "r",
    config: PitQueryConfig | None = None,
) -> pd.DataFrame:
    if select_left is None:
        select_left = ["*"]
    if config is None:
        config = PitQueryConfig()

    _require_columns(conn, left_table, [as_of_column], "Left")
    _require_columns(conn, right_table, [as_of_column, right_published_at], "Right")

    left_cols = ", ".join(f"{left_alias}.{c}" for c in select_left)
    right_cols = ", ".join(f"{right_alias}.{c}" for c in (select_right or []))
    if select_right:
        all_cols = f"{left_cols}, {right_cols}"
    else:
        all_cols = left_cols

    right_event_time = f"{right_alias}.{as_of_column}"
    right_published_at_col = f"{right_alias}.{right_published_at}"

    join_conditions = []
    for col in on:
        join_conditions.append(f"{left_alias}.{col} = {right_alias}.{col}")
    join_conditions.append(f"{right_published_at_col} <= {left_alias}.{as_of_column}")

    join_sql = " AND ".join(join_conditions)

    sql = f"""
        SELECT {all_cols}
        FROM {left_table} AS {left_alias}
        ASOF JOIN {right_table} AS {right_alias}
          ON {join_sql}
    """

    if config.strict:
        lookahead_warnings = validate_no_lookahead(sql)
        if lookahead_warnings:
            raise ValueError(
                "Look-ahead patterns detected in query:\n"
                + "\n".join(lookahead_warnings)
            )

    return conn.execute(sql).fetchdf()


def pit_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    as_of_time: Any,
    config: PitQueryConfig | None = None,
) -> pd.DataFrame:
    if config is None:
        config = PitQueryConfig()

    substituted = sql.replace("{as_of_time}", "?")
    warnings = validate_no_lookahead(substituted)

    if config.strict and warnings:
        raise ValueError(
            "Look-ahead patterns detected:\n" + "\n".join(warnings)
        )

    return conn.execute(substituted, [as_of_time]).fetchdf()
