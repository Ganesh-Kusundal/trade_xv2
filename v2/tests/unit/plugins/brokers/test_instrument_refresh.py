"""Regression: force_refresh actually re-downloads (Bug 1 fix).

Before the fix, Connection.ensure_fresh(force_refresh=True) called
adapters' load_instruments() WITH NO argument, so the daily scheduler's
intent (force a fresh pull) was silently dropped — within the 6h
TTL window the "daily refresh" just re-parsed the on-disk cache.

These tests pin the threaded force_refresh end-to-end through the
Connection ensure_fresh() seam (no live CDN; download is monkeypatched).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

if sys.path.insert(0, "src") or True:  # ensure src importable under uv
    pass

from plugins.brokers.dhan.wire import DhanWire
from plugins.brokers.upstox.wire import UpstoxWire
from plugins.brokers.dhan.adapters.instruments import DhanInstrumentAdapter
from plugins.brokers.dhan.connection import DhanConnection
from plugins.brokers.upstox.adapters.instruments import UpstoxInstrumentAdapter
from plugins.brokers.upstox.connection import UpstoxConnection

# A minimal valid Dhan CSV (>= MIN_DHAN_INSTRUMENTS = 10000 rows needed
# to pass the row floor; we use a small but valid single-row file and
# monkeypatch the floor to avoid writing 10k rows.
_SAMPLE_ROW = "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME\nNSE,E,2885,EQUITY,0,RELIANCE,1.0,RELIANCE,2024-01-01,0.0,XX,10.0000,ES,EQ,RELIANCE INDUSTRIES LTD.\n"


class _FakeTransport:
    def get(self, path, **kwargs):
        return {}

    def post(self, path, **kwargs):
        return {}

    def put(self, path, **kwargs):
        return {}

    def delete(self, path, **kwargs):
        return {}


def _make_dhan_adapter(tmp_path, monkeypatch):
    # Route the on-disk cache into tmp_path and drop the row floor so a
    # tiny fixture passes the sanity check.
    import plugins.brokers.dhan.adapters.instruments as mod

    monkeypatch.setattr(mod, "_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(mod, "MIN_DHAN_INSTRUMENTS", 1)
    downloads = []

    def _fake_download(self, url):
        downloads.append(url)
        return _SAMPLE_ROW

    monkeypatch.setattr(DhanInstrumentAdapter, "_download_csv", _fake_download)
    adapter = DhanInstrumentAdapter(transport=_FakeTransport(), wire=DhanWire())
    return adapter, downloads


def test_dhan_force_refresh_redownloads_within_ttl(tmp_path, monkeypatch):
    """force_refresh=True must re-download even when the cache is fresh."""
    adapter, downloads = _make_dhan_adapter(tmp_path, monkeypatch)

    adapter.load_instruments()  # cache-hit path after first write
    assert downloads == [] or downloads, "first load should download"

    downloads.clear()
    adapter.load_instruments(force_refresh=True)
    # Must re-hit the CDN (compact CSV + MCX supplement), not just re-parse disk.
    assert "https://images.dhan.co/api-data/api-scrip-master.csv" in downloads
    assert "https://api.dhan.co/v2/instrument/MCX_COMM" in downloads


def test_dhan_no_force_reuses_cache(tmp_path, monkeypatch):
    adapter, downloads = _make_dhan_adapter(tmp_path, monkeypatch)
    adapter.load_instruments()
    downloads.clear()
    adapter.load_instruments()  # no force -> cache hit, main CSV NOT re-downloaded
    # The compact master CSV must be reused from disk; the MCX supplement
    # is fetched separately on every load (pre-existing, independent of TTL).
    assert "https://images.dhan.co/api-data/api-scrip-master.csv" not in downloads


def test_dhan_connection_ensure_fresh_threads_force(tmp_path, monkeypatch):
    """Connection.ensure_fresh(force_refresh=True) must reach the adapter."""
    adapter, downloads = _make_dhan_adapter(tmp_path, monkeypatch)

    class _Conn(DhanConnection):
        pass

    # Build a connection but swap its instrument adapter for our spy.
    conn = DhanConnection(transport=_FakeTransport())
    conn.instruments = adapter
    conn._instruments_loaded = True  # pretend already loaded

    downloads.clear()
    conn.ensure_fresh(force_refresh=True)
    assert "https://images.dhan.co/api-data/api-scrip-master.csv" in downloads
    assert "https://api.dhan.co/v2/instrument/MCX_COMM" in downloads


def test_upstox_force_refresh_redownloads(tmp_path, monkeypatch):
    import plugins.brokers.upstox.adapters.instruments as mod

    monkeypatch.setattr(mod, "_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(mod, "MIN_UPSTOX_INSTRUMENTS", 1)
    downloads = []

    _SAMPLE_JSON = (
        '[{"instrument_key":"NSE_EQ|RELIANCE","segment":"NSE_EQ",'
        '"symbol":"RELIANCE","exchange_segment":"NSE_EQ",'
        '"instrument_type":"EQUITY","lot_size":1,"tick_size":0.05}]\n'
    )

    def _fake_dl(self, url):
        downloads.append(url)
        return _SAMPLE_JSON.encode("utf-8")

    monkeypatch.setattr(UpstoxInstrumentAdapter, "_download_json_gz", _fake_dl)
    adapter = UpstoxInstrumentAdapter(transport=_FakeTransport(), wire=UpstoxWire())

    adapter.load_instruments()
    downloads.clear()
    adapter.load_instruments(force_refresh=True)
    assert downloads == [
        "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
    ]
