"""Shared Dhan test fixtures (single source of truth).

Previously ``SAMPLE_ROWS`` / ``FakeHttpClient`` were duplicated in
``test_edge_cases.py`` and ``test_chaos.py`` while other tests imported them from
a ghost ``brokers.dhan.tests.conftest`` package that no longer exists. They now
live here; every test imports from ``tests.support.brokers.dhan.fixtures``.
"""

from __future__ import annotations

from typing import Any

SAMPLE_ROWS = [
    # ── Index ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY",
        "SEM_SMST_SECURITY_ID": "13",
        "SEM_EXM_EXCH_ID": "IDX_I",
        "SEM_INSTRUMENT_NAME": "INDEX",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Nifty 50",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── BSE Equity ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "532",
        "SEM_EXM_EXCH_ID": "BSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 0.05,
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
        "SM_SYMBOL_NAME": "RELIANCE INDUSTRIES LTD",
    },
    # ── TCS Equity ──
    {
        "SEM_TRADING_SYMBOL": "TCS",
        "SEM_SMST_SECURITY_ID": "11536",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 10,
        "SEM_CUSTOM_SYMBOL": "Tata Consultancy Services",
        "SM_SYMBOL_NAME": "TATA CONSULTANCY SERVICES LTD",
    },
    # ── NSE F&O Option (CE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-CE",
        "SEM_SMST_SECURITY_ID": "55000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 CALL",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Option (PE) ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-25000-PE",
        "SEM_SMST_SECURITY_ID": "55001",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 25000,
        "SEM_OPTION_TYPE": "PE",
        "SEM_CUSTOM_SYMBOL": "NIFTY 26 JUN 25000 PUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── NSE F&O Future ──
    {
        "SEM_TRADING_SYMBOL": "NIFTY-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "55100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTIDX",
        "SEM_LOT_UNITS": 75,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "NIFTY JUN FUT",
        "SM_SYMBOL_NAME": "NIFTY",
    },
    # ── MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "466500",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUN FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-20Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466501",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-20",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL JUL FUT",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── MCX Commodity Option ──
    {
        "SEM_TRADING_SYMBOL": "CRUDEOIL-18Jun2026-5000-CE",
        "SEM_SMST_SECURITY_ID": "466600",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "OPTFUT",
        "SEM_LOT_UNITS": 100,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-06-18",
        "SEM_STRIKE_PRICE": 5000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "CRUDEOIL 18 JUN 5000 CALL",
        "SM_SYMBOL_NAME": "CRUDEOIL",
    },
    # ── GOLDM MCX Commodity Future ──
    {
        "SEM_TRADING_SYMBOL": "GOLDM-03Jul2026-FUT",
        "SEM_SMST_SECURITY_ID": "466584",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-07-03",
        "SEM_CUSTOM_SYMBOL": "GOLDM JUL FUT",
        "SM_SYMBOL_NAME": "GOLDM",
    },
    # ── GOLD MCX Commodity Future (near-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD AUG FUT",
        "SEM_SMST_SECURITY_ID": "466583",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-08-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── GOLD MCX Commodity Future (far-month) ──
    {
        "SEM_TRADING_SYMBOL": "GOLD OCT FUT",
        "SEM_SMST_SECURITY_ID": "483079",
        "SEM_EXM_EXCH_ID": "MCX_COMM",
        "SEM_INSTRUMENT_NAME": "FUTCOM",
        "SEM_LOT_UNITS": 1,
        "SEM_TICK_SIZE": 1.0,
        "SEM_EXPIRY_DATE": "2026-10-05",
        "SEM_CUSTOM_SYMBOL": "GOLD",
        "SM_SYMBOL_NAME": "GOLD",
    },
    # ── BSE F&O Option (SENSEX) ──
    {
        "SEM_TRADING_SYMBOL": "SENSEX-26Jun2026-80000-CE",
        "SEM_SMST_SECURITY_ID": "70000",
        "SEM_EXM_EXCH_ID": "BSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTIDX",
        "SEM_LOT_UNITS": 10,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 80000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "SENSEX 26 JUN 80000 CALL",
        "SM_SYMBOL_NAME": "SENSEX",
    },
    # ── Currency Future (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "80000",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "FUTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "USDINR JUN FUT",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Currency Option (NSE) ──
    {
        "SEM_TRADING_SYMBOL": "USDINR-26Jun2026-85-CE",
        "SEM_SMST_SECURITY_ID": "80100",
        "SEM_EXM_EXCH_ID": "NSE_CURRENCY",
        "SEM_INSTRUMENT_NAME": "OPTCUR",
        "SEM_LOT_UNITS": 1000,
        "SEM_TICK_SIZE": 0.0025,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 85,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "USDINR 26 JUN 85 CALL",
        "SM_SYMBOL_NAME": "USDINR",
    },
    # ── Stock F&O Option (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-3000-CE",
        "SEM_SMST_SECURITY_ID": "60000",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "OPTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_STRIKE_PRICE": 3000,
        "SEM_OPTION_TYPE": "CE",
        "SEM_CUSTOM_SYMBOL": "RELIANCE 26 JUN 3000 CALL",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
    # ── Stock F&O Future (RELIANCE) ──
    {
        "SEM_TRADING_SYMBOL": "RELIANCE-26Jun2026-FUT",
        "SEM_SMST_SECURITY_ID": "60100",
        "SEM_EXM_EXCH_ID": "NSE_FNO",
        "SEM_INSTRUMENT_NAME": "FUTSTK",
        "SEM_LOT_UNITS": 250,
        "SEM_TICK_SIZE": 0.05,
        "SEM_EXPIRY_DATE": "2026-06-26",
        "SEM_CUSTOM_SYMBOL": "RELIANCE JUN FUT",
        "SM_SYMBOL_NAME": "RELIANCE",
    },
]



def _quote_entry(sid: str) -> dict[str, Any]:
    return {
        "last_price": 2500.0,
        "net_change": 10.0,
        "volume": 100000,
        "ohlc": {"open": 2490.0, "high": 2510.0, "low": 2480.0, "close": 2495.0},
        "depth": {
            "buy": [{"price": 2499.0, "quantity": 100, "orders": 2}],
            "sell": [{"price": 2501.0, "quantity": 150, "orders": 3}],
        },
    }


class FakeHttpClient:
    """Offline stand-in for the Dhan HTTP client with marketfeed shapes."""

    def __init__(self):
        self.client_id = "test"
        self.access_token = "test"

    def get(self, endpoint, **kw):
        if "fundlimit" in endpoint or "fund" in endpoint:
            return {
                "data": {
                    "availabelBalance": 100000.0,
                    "utilizedAmount": 0.0,
                    "sodLimit": 100000.0,
                }
            }
        if "orders" in endpoint or "trades" in endpoint:
            return {"data": []}
        return {"data": []}

    def post(self, endpoint, json=None):
        body = json or {}
        if endpoint.startswith("/marketfeed/"):
            # body is {segment: [security_id, ...]}
            data: dict[str, Any] = {}
            for segment, sids in body.items():
                data[segment] = {str(sid): _quote_entry(str(sid)) for sid in sids}
            return {"data": data}
        if "charts" in endpoint or "historical" in endpoint:
            return {
                "data": {
                    "open": [100.0],
                    "high": [110.0],
                    "low": [95.0],
                    "close": [105.0],
                    "volume": [1000],
                    "timestamp": [1718601600],
                    "open_interest": [0],
                }
            }
        return {"data": []}

    def put(self, endpoint, json=None):
        return {"data": {}}

    def delete(self, endpoint):
        return {"data": []}


__all__ = ["FakeHttpClient", "SAMPLE_ROWS"]
