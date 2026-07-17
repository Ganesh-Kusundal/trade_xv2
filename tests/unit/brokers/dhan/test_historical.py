"""Unit tests for HistoricalAdapter."""

import pandas as pd

from brokers.dhan.data.historical import HistoricalAdapter


def test_intraday_epoch_parses_as_utc_aware_not_naive(fake_client, resolver):
    """Regression test: Dhan's epoch field is genuine UTC. Parsing it
    without utc=True produced a naive datetime64 that
    datalake.ingestion.normalize.ensure_timestamp_dtype()'s "naive ->
    assume already IST" fallback then left unconverted -- candles landed
    5.5h off the true IST session for ~11 months (e.g. a 09:15 IST open
    stored as "03:45"). This pins the fix: the epoch must come out
    tz-aware and equal to the exact UTC instant it represents."""
    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,  # 2025-01-02 01:15:00 UTC
                    "open": 2440,
                    "high": 2445,
                    "low": 2438,
                    "close": 2443,
                    "volume": 5000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    df = adapter.get_historical("RELIANCE", "NSE", "2026-01-02", "2026-01-02", timeframe="5")

    ts = df["timestamp"].iloc[0]
    assert ts.tzinfo is not None, "epoch must parse tz-aware, not naive"
    assert ts == pd.Timestamp("2025-01-02 01:15:00", tz="UTC")


def test_intraday_epoch_converts_to_correct_ist_through_full_pipeline(fake_client, resolver):
    """End-to-end: the same epoch, run through the full normalize
    pipeline (what actually writes to the datalake), must land on the
    correct IST wall-clock instant, not a 5.5h-shifted one."""
    from datalake.ingestion.normalize import normalize_to_canonical

    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,  # 2025-01-02 01:15:00 UTC == 06:45 IST
                    "open": 2440,
                    "high": 2445,
                    "low": 2438,
                    "close": 2443,
                    "volume": 5000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    df = adapter.get_historical("RELIANCE", "NSE", "2026-01-02", "2026-01-02", timeframe="5")
    normalized = normalize_to_canonical(df, "RELIANCE", "NSE")

    ts = normalized["timestamp"].iloc[0]
    assert ts.tzinfo is None  # datalake schema: naive, already-IST-labeled
    assert ts == pd.Timestamp("2025-01-02 06:45:00")


def test_daily_uses_historical_endpoint(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/historical",
        {
            "data": [
                {
                    "date": "2026-01-02",
                    "open": 2440,
                    "high": 2460,
                    "low": 2435,
                    "close": 2455,
                    "volume": 1000000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-31", timeframe="1D")

    # Verify the daily endpoint was used
    assert len(fake_client.calls_for("POST", "/charts/historical")) == 1
    # Intraday endpoint should NOT have been called
    assert len(fake_client.calls_for("POST", "/charts/intraday")) == 0


def test_intraday_uses_intraday_endpoint(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,
                    "open": 2440,
                    "high": 2445,
                    "low": 2438,
                    "close": 2443,
                    "volume": 5000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("RELIANCE", "NSE", "2026-01-02", "2026-01-02", timeframe="5")

    # Verify the intraday endpoint was used
    assert len(fake_client.calls_for("POST", "/charts/intraday")) == 1
    # Daily endpoint should NOT have been called
    assert len(fake_client.calls_for("POST", "/charts/historical")) == 0

    # Verify the interval was included in the payload
    payloads = fake_client.calls_for("POST", "/charts/intraday")
    assert payloads[0]["interval"] == "5"


def test_mcx_session_times(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,
                    "open": 72000,
                    "high": 72100,
                    "low": 71900,
                    "close": 72050,
                    "volume": 100,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("GOLD", "MCX", "2026-01-02", "2026-01-02", timeframe="5")

    payloads = fake_client.calls_for("POST", "/charts/intraday")
    assert len(payloads) == 1
    payload = payloads[0]
    # MCX session opens at 09:00 and closes at 23:30
    assert payload["fromDate"].endswith("09:00:00")
    assert payload["toDate"].endswith("23:30:00")


def test_instrument_type_detection(resolver):
    """Verify _get_instrument_type maps correctly: INDEX→EQUITY, NFO→OPTIDX, MCX→FUTCOM."""
    # NIFTY is an INDEX instrument → should map to "EQUITY"
    nifty = resolver.resolve("NIFTY", "INDEX")
    assert HistoricalAdapter._get_instrument_type(nifty) == "EQUITY"

    # RELIANCE is an EQUITY instrument → should map to "EQUITY"
    reliance = resolver.resolve("RELIANCE", "NSE")
    assert HistoricalAdapter._get_instrument_type(reliance) == "EQUITY"

    # NIFTY options on NFO → should map to "OPTIDX"
    nifty_opt = resolver.resolve("NIFTY 26 JUN 25000 CE", "NFO")
    assert HistoricalAdapter._get_instrument_type(nifty_opt) == "OPTIDX"

    # GOLD futures on MCX → should map to "FUTCOM"
    gold = resolver.resolve("GOLD AUG FUT", "MCX")
    assert HistoricalAdapter._get_instrument_type(gold) == "FUTCOM"


def test_parse_dataframe(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/historical",
        {
            "data": [
                {
                    "date": "2026-01-02",
                    "open": 2440,
                    "high": 2460,
                    "low": 2435,
                    "close": 2455,
                    "volume": 1000000,
                },
                {
                    "date": "2026-01-03",
                    "open": 2455,
                    "high": 2475,
                    "low": 2450,
                    "close": 2470,
                    "volume": 1200000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    df = adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-31", timeframe="1D")

    assert isinstance(df, pd.DataFrame)
    required_cols = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
        "symbol",
        "exchange",
        "timeframe",
    }
    assert required_cols.issubset(set(df.columns))
    assert len(df) == 2
    assert list(df.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
        "symbol",
        "exchange",
        "timeframe",
    ]
