"""OE-01 golden parity: SQL FeatureViews vs Python FeaturePipeline.

Proves overlapping v_feature_* columns match FeaturePipeline on a fixed OHLCV
window (± float tolerance). Uses deterministic fixture data (same pattern as
tests/integration/quant/golden/feature_parity.json).

Run: PYTHONPATH=src pytest tests/integration/quant/test_views_pipeline_parity.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from analytics.pipeline.features import ROC, RelativeVolume, VWAP, VolumeSMA
from analytics.pipeline.pipeline import FeaturePipeline
from tests.fixtures.data_helpers import make_ohlcv

# ponytail: load features.py directly — analytics.views.__init__ pulls broken datalake chain
_FEATURES_PATH = (
    Path(__file__).resolve().parents[3] / "src" / "analytics" / "views" / "features.py"
)


def _feature_views():
    spec = importlib.util.spec_from_file_location("_oe01_feature_views", _FEATURES_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FeatureViews()

# ponytail: single-day window keeps domain VWAP aligned with SQL daily partition
_PARITY_BARS = 200
_PARITY_SYMBOL = "RELIANCE"
_PARITY_SEED = 42
_FLOAT_RTOL = 1e-9
_FLOAT_ATOL = 1e-6

# SQL view column -> FeaturePipeline output column
_PARITY_PAIRS: tuple[tuple[str, str], ...] = (
    ("relative_volume", "relative_volume"),
    ("avg_volume_20", "avg_volume_20"),
    ("roc_5", "roc_5"),
    ("roc_10", "roc_10"),
    ("roc_20", "roc_20"),
    ("vwap", "vwap"),
)


def _parity_ohlcv() -> pd.DataFrame:
    """Fixed single-symbol window (deterministic, no broker mocks)."""
    return make_ohlcv(
        n=_PARITY_BARS,
        symbol=_PARITY_SYMBOL,
        seed=_PARITY_SEED,
        start_price=100.0,
    )


def _pipeline_features(df: pd.DataFrame) -> pd.DataFrame:
    pipeline = (
        FeaturePipeline()
        .add(VWAP())
        .add(RelativeVolume(period=20))
        .add(VolumeSMA(name="avg_volume_20", period=20))
        .add(ROC(name="roc_5", period=5))
        .add(ROC(name="roc_10", period=10))
        .add(ROC(name="roc_20", period=20))
    )
    return pipeline.run(df)


def _views_features(df: pd.DataFrame) -> pd.DataFrame:
    candles = df.drop(columns=["symbol"]).copy()
    candles["timestamp"] = pd.to_datetime(candles["timestamp"], utc=True).dt.tz_localize(None)
    for col in ("open", "high", "low", "close", "volume"):
        candles[col] = candles[col].astype("float64")

    conn = duckdb.connect()
    try:
        conn.register("parity_candles", candles)
        conn.execute(
            f"""
            CREATE OR REPLACE VIEW v_candles_1m AS
            SELECT
                timestamp,
                '{_PARITY_SYMBOL}' AS symbol,
                'NSE' AS exchange,
                open,
                high,
                low,
                close,
                CAST(volume AS BIGINT) AS volume,
                0 AS oi
            FROM parity_candles
            """
        )
        _feature_views().create_views(conn)
        return conn.execute(
            """
            SELECT
                c.timestamp,
                c.symbol,
                vol.relative_volume,
                vol.avg_volume_20,
                mom.roc_5,
                mom.roc_10,
                mom.roc_20,
                vw.vwap
            FROM v_candles_1m AS c
            INNER JOIN v_feature_volume AS vol
                USING (symbol, timestamp)
            INNER JOIN v_feature_momentum AS mom
                USING (symbol, timestamp)
            INNER JOIN v_feature_vwap AS vw
                USING (symbol, timestamp)
            ORDER BY c.timestamp
            """
        ).fetchdf()
    finally:
        conn.close()


@pytest.mark.integration
def test_views_pipeline_feature_parity_golden_window() -> None:
    """v_feature_* SQL path matches FeaturePipeline on fixed OHLCV window."""
    ohlcv = _parity_ohlcv()
    py_df = _pipeline_features(ohlcv)
    py_df["timestamp"] = pd.to_datetime(py_df["timestamp"], utc=True).dt.tz_localize(None)
    sql_df = _views_features(ohlcv)
    sql_df["timestamp"] = pd.to_datetime(sql_df["timestamp"])

    assert len(sql_df) == len(py_df) == _PARITY_BARS

    merged = sql_df.merge(
        py_df,
        on=["timestamp", "symbol"],
        suffixes=("_sql", "_py"),
        validate="one_to_one",
    )
    assert len(merged) == _PARITY_BARS

    for sql_col, py_col in _PARITY_PAIRS:
        sql_vals = merged[f"{sql_col}_sql"].astype(float).to_numpy()
        py_vals = merged[f"{py_col}_py"].astype(float).to_numpy()
        mask = np.isfinite(sql_vals) & np.isfinite(py_vals)
        assert mask.any(), f"No comparable values for {sql_col}"
        np.testing.assert_allclose(
            sql_vals[mask],
            py_vals[mask],
            rtol=_FLOAT_RTOL,
            atol=_FLOAT_ATOL,
            err_msg=f"parity mismatch on {sql_col} vs pipeline {py_col}",
        )
