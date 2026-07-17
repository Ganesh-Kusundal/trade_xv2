"""Afternoon Expansion Scanner — 09:50 IST decision candidate ranking.

Selects equities that have historically shown large intraday expansion
*after* the morning decision candle, ranked by historical propensity,
gated on that same morning's activity. Used as a daily watchlist for
09:50 → 15:15 IST trades targeting a 5–10% move.

Data source: local Parquet lake (`data/lake`). Lake 1m timestamps are stored
as naive IST wall-clock (no UTC shift); all window bounds below are expressed
directly in IST.

Invariants (zero look-ahead, checked in tests):
- Morning features use only bars up to DECISION_END.
- Historical propensity uses only days strictly before the trade date.
- The realized afternoon outcome is exposed for *backchecking* only and
  never enters WHERE/ORDER BY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from analytics.sector.mapping import SectorMapper
from datalake.core.paths import timeframe_partition_dir
from datalake.core.symbols import normalize_symbol_for_storage
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

# Lake 1m timestamps are stored as naive IST wall-clock (no UTC shift), so
# session bounds are expressed directly in IST.
MORNING_START = "09:15:00"  # 09:15 IST open
DECISION_END = "09:50:00"  # 09:50 IST (decision candle close)
SESSION_END = "15:15:00"  # 15:15 IST close


@dataclass
class AfternoonExpansionConfig:
    """Tunable parameters for the afternoon expansion scan."""

    top_k: int = 5
    min_rvol: float = 1.5
    min_abs_morning_gain: float = 0.30
    min_hist_sessions: int = 20
    min_hit_ge5: float = 0.05
    target_mfe_lo: float = 5.0
    target_mfe_hi: float = 10.0
    lookback_days: int = 60
    # Number of morning bars expected for a complete window (375 1m bars/day
    # span 09:15→15:15; 09:15→09:50 is ~36 bars; require >=30).
    min_morning_bars: int = 30

    def to_sql_params(self) -> dict:
        return {
            "MIN_RVOL": self.min_rvol,
            "MIN_ABS_MORNING_GAIN": self.min_abs_morning_gain,
            "MIN_HIST_SESSIONS": self.min_hist_sessions,
            "MIN_HIT_GE5": self.min_hit_ge5,
            "TARGET_MFE_LO": self.target_mfe_lo,
            "TARGET_MFE_HI": self.target_mfe_hi,
            "MORNING_START": MORNING_START,
            "DECISION_END": DECISION_END,
            "SESSION_END": SESSION_END,
            "MIN_MORNING_BARS": self.min_morning_bars,
        }


def _parquet_glob(root: str) -> str:
    return str(Path(timeframe_partition_dir(root, "1m")) / "symbol=*/data.parquet")


def resolve_trade_date(
    con: duckdb.DuckDBPyConnection, trade_date: str | None, root: str = DEFAULT_DATA_ROOT
) -> str:
    """Return trade_date, or the latest date present in the lake if None."""
    if trade_date:
        return trade_date
    row = con.execute(
        f"""
        SELECT max(CAST(timestamp AS DATE))::VARCHAR
        FROM read_parquet('{_parquet_glob(root)}', hive_partitioning := true)
        """
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError("No candle dates found in datalake")
    return row[0]


def scan_afternoon_expansion(
    trade_date: str,
    config: AfternoonExpansionConfig | None = None,
    root: str = DEFAULT_DATA_ROOT,
) -> pd.DataFrame:
    """Rank 09:50 IST candidates by historical afternoon-expansion propensity.

    Returns one row per symbol available on ``trade_date`` that passes the
    activity gates and has sufficient historical propensity. Columns include the
    historical hit-rates AND the realized afternoon move for ``trade_date``
    (the latter is for backchecking, never used for ranking).
    """
    cfg = config or AfternoonExpansionConfig()
    p = cfg.to_sql_params()
    glob = _parquet_glob(root)
    sql = f"""
    WITH bars AS (
      SELECT
        symbol,
        timestamp,
        CAST(timestamp AS DATE) AS td,
        open, high, low, close, volume,
        CAST(timestamp AS TIME) AS tt
      FROM read_parquet('{glob}', hive_partitioning := true)
      WHERE CAST(timestamp AS DATE)
            BETWEEN DATE '{trade_date}' - INTERVAL {cfg.lookback_days} DAY
            AND DATE '{trade_date}'
    ),
    morn AS (
      SELECT
        symbol, td,
        arg_min(open, timestamp) AS day_open,
        max(high) AS high_m,
        min(low) AS low_m,
        arg_max(close, timestamp) AS c950,
        sum(volume) AS morning_vol,
        count(*) AS morning_bars
      FROM bars
      WHERE tt BETWEEN TIME '{p['MORNING_START']}' AND TIME '{p['DECISION_END']}'
      GROUP BY 1, 2
    ),
    aft AS (
      SELECT
        symbol, td,
        max(high) AS ah,
        min(low) AS al,
        arg_max(close, timestamp) AS c_eod
      FROM bars
      WHERE tt > TIME '{p['DECISION_END']}' AND tt <= TIME '{p['SESSION_END']}'
      GROUP BY 1, 2
    ),
    joined AS (
      SELECT
        m.symbol, m.td, m.c950, m.day_open, m.morning_vol, m.morning_bars,
        (m.c950 - m.day_open) / NULLIF(m.day_open, 0) * 100 AS morning_gain,
        CASE
          WHEN m.high_m > m.low_m
          THEN (m.c950 - m.low_m) / (m.high_m - m.low_m)
        END AS close_in_range,
        (a.ah - a.al) / NULLIF(m.c950, 0) * 100 AS rest_range_pct,
        greatest(a.ah - m.c950, m.c950 - a.al) / NULLIF(m.c950, 0) * 100
          AS rest_mfe_pct,
        abs(a.c_eod - m.c950) / NULLIF(m.c950, 0) * 100 AS rest_close_abs_pct
      FROM morn m
      LEFT JOIN aft a USING (symbol, td)
      WHERE m.morning_bars >= {p['MIN_MORNING_BARS']}
    ),
    hist AS (
      SELECT
        symbol,
        count(*) AS sessions,
        avg(CASE WHEN rest_mfe_pct >= {p['TARGET_MFE_LO']} THEN 1.0 ELSE 0.0 END) AS hit_ge5,
        avg(
          CASE
            WHEN rest_mfe_pct BETWEEN {p['TARGET_MFE_LO']} AND {p['TARGET_MFE_HI']}
            THEN 1.0 ELSE 0.0
          END
        ) AS hit_5_10,
        avg(rest_mfe_pct) AS avg_mfe,
        approx_quantile(rest_mfe_pct, 0.9) AS p90_mfe
      FROM joined
      WHERE td < DATE '{trade_date}'
      GROUP BY 1
      HAVING count(*) >= {p['MIN_HIST_SESSIONS']}
    ),
    mvol_base AS (
      SELECT symbol, avg(morning_vol) AS avg_morning_vol
      FROM morn
      WHERE td < DATE '{trade_date}'
      GROUP BY 1
    ),
    today AS (
      SELECT
        j.*,
        j.morning_vol / NULLIF(b.avg_morning_vol, 0) AS rvol
      FROM joined j
      LEFT JOIN mvol_base b USING (symbol)
      WHERE j.td = DATE '{trade_date}'
    )
    SELECT
      t.symbol,
      t.c950,
      t.morning_gain,
      t.close_in_range,
      t.rvol,
      t.morning_bars,
      h.sessions AS hist_sessions,
      h.hit_ge5,
      h.hit_5_10,
      h.avg_mfe,
      h.p90_mfe,
      t.rest_mfe_pct AS realized_mfe_after_0950,
      t.rest_range_pct AS realized_range_after_0950
    FROM today t
    JOIN hist h USING (symbol)
    WHERE t.rvol > {p['MIN_RVOL']}
      AND abs(t.morning_gain) > {p['MIN_ABS_MORNING_GAIN']}
      AND h.hit_ge5 >= {p['MIN_HIT_GE5']}
    ORDER BY h.hit_ge5 DESC, t.rvol DESC, h.avg_mfe DESC
    """
    return duckdb.connect().execute(sql).fetchdf()


def industry_diversified_top_k(
    passes: pd.DataFrame, k: int, mapper: SectorMapper | None = None
) -> pd.DataFrame:
    """Walk the rvol-ranked list; keep at most one symbol per sector."""
    mapper = mapper or SectorMapper.default()
    df = mapper.assign_sectors(passes.reset_index(drop=True))
    picked: list[int] = []
    seen: set[str] = set()
    for i, row in df.iterrows():
        sector = row["sector"]
        if sector in seen:
            continue
        seen.add(sector)
        picked.append(i)
        if len(picked) >= k:
            break
    return df.loc[picked].reset_index(drop=True)


# Columns surfaced to callers / notebook.
RESULT_COLUMNS = [
    "symbol",
    "sector",
    "c950",
    "morning_gain",
    "rvol",
    "close_in_range",
    "hit_ge5",
    "hit_5_10",
    "avg_mfe",
    "p90_mfe",
    "hist_sessions",
    "realized_mfe_after_0950",
    "realized_range_after_0950",
]


def run_scan(
    trade_date: str | None = None,
    config: AfternoonExpansionConfig | None = None,
    pick: bool = True,
    root: str = DEFAULT_DATA_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """High-level entry: returns ``(passes, picks)``.

    ``passes`` is the full ranked list; ``picks`` is the Top-K
    sector-diversified subset (empty if ``pick`` is False).
    """
    cfg = config or AfternoonExpansionConfig()
    con = duckdb.connect()
    date = resolve_trade_date(con, trade_date, root=root)
    passes = scan_afternoon_expansion(date, config=cfg, root=root)
    mapper = SectorMapper.default()
    passes = mapper.assign_sectors(passes)
    if not pick:
        return passes, passes.iloc[0:0]
    picks = industry_diversified_top_k(passes, k=cfg.top_k)
    return passes, picks
