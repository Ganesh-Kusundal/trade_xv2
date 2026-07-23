"""Focused live probe: is Dhan historical data coming through?

Read-only. Connects via the standard gateway bootstrap and fetches a few
daily + intraday windows, printing shape/first/last rows so we can confirm
real candles (not empty frames) flow through the src provider.
"""

import contextlib
import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _SCRIPTS)

from _connect import bootstrap_or_exit  # noqa: E402

CASES = [
    ("RELIANCE", "NSE", "1D", "NSE Equity Daily"),
    ("RELIANCE", "NSE", "5m", "NSE Equity 5min"),
    ("NIFTY", "IDX_I", "1D", "Index Daily"),
]


def main() -> int:
    gw = bootstrap_or_exit("dhan", load_instruments=True)
    print(f"Gateway up. instruments={gw.describe().get('instrument_count', '?')}\n")
    any_ok = False
    try:
        for symbol, exchange, tf, label in CASES:
            try:
                df = gw.history(symbol, exchange, timeframe=tf, lookback_days=10)
                n = 0 if df is None else len(df)
                if n > 0:
                    any_ok = True
                    first_ts = df["timestamp"].iloc[0]
                    last_ts = df["timestamp"].iloc[-1]
                    last_close = df["close"].iloc[-1]
                    print(f"✅ {label:20s} {symbol}/{exchange} {tf}: {n} bars")
                    print(f"     first={first_ts}  last={last_ts}  last_close={last_close}")
                else:
                    print(f"❌ {label:20s} {symbol}/{exchange} {tf}: EMPTY frame")
            except Exception as e:  # noqa: BLE001
                print(f"❌ {label:20s} {symbol}/{exchange} {tf}: {type(e).__name__}: {e}")
    finally:
        with contextlib.suppress(Exception):
            gw._conn.close()
    print("\nRESULT:", "HISTORICAL DATA IS COMING" if any_ok else "NO HISTORICAL DATA")
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(main())
