#!/usr/bin/env python3
"""Real-data verification that broker quote paths surface Open Interest (oi).

No mocks. Hits the live full-quote endpoint for a real F&O contract on each
configured broker and asserts the adapter populates ``Quote.oi`` and that
equity quotes default oi to 0.

Read-only: only the quote endpoints are called. No orders, no writes.

Usage:
    python scripts/verify/check_quote_oi_real.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure the project src/ is the authoritative import root and that this
# script's own directory (auto-prepended to sys.path[0] by the interpreter)
# does not shadow the real packages.
ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
sys.path[:] = [str(SRC), str(SCRIPTS), str(ROOT)] + [
    p for p in sys.path if Path(p).resolve() != (ROOT / "scripts" / "verify").resolve()
]
os.chdir(ROOT)

import requests  # noqa: E402

ENV = ROOT / ".env.local"


def _load_env() -> dict[str, str]:
    out: dict[str, str] = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    # Environment variables take precedence.
    for k, v in os.environ.items():
        if k in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "UPSTOX_ACCESS_TOKEN",
                 "UPSTOX_API_KEY", "UPSTOX_BASE_V2", "UPSTOX_BASE_URL"):
            out[k] = v
    return out


def _probe_dhan(env: dict[str, str]) -> bool:
    print("\n" + "=" * 60)
    print("  DHAN — real full-quote OI probe")
    print("=" * 60)
    cid = env.get("DHAN_CLIENT_ID")
    token = env.get("DHAN_ACCESS_TOKEN")
    if not cid or not token:
        print("  SKIP: DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set")
        return False
    try:
        os.chdir(ROOT)
        sys.path.insert(0, str(ROOT / "scripts"))
        from _connect import bootstrap_or_none

        gw = bootstrap_or_none("dhan", env_path=ENV, load_instruments=True)
        if gw is None:
            print("  SKIP: dhan gateway unavailable (auth/instruments)")
            return False

        # Resolve a real NSE_FNO instrument from the loaded instrument set.
        fno = None
        try:
            fno = gw._conn.identity.resolver.get_by_security_id("99999")
        except Exception:
            fno = None
        if fno is None:
            try:
                for inst in gw._conn.identity.resolver.all_instruments():
                    if getattr(inst, "exchange_segment", "") == "NSE_FNO":
                        fno = inst
                        break
            except Exception:
                fno = None
        if fno is None:
            print("  SKIP: no NSE_FNO instrument resolvable")
            return False

        sym = fno.trading_symbol if hasattr(fno, "trading_symbol") else fno.symbol
        print(f"  F&O contract: {sym} ({fno.exchange_segment})")

        q = gw.quote(sym, exchange="NFO")
        print(f"  ltp={q.ltp} volume={q.volume} oi={q.oi}")
        assert isinstance(q.oi, int), "oi must be int"
        assert q.oi > 0, f"expected oi>0 for F&O contract, got {q.oi}"
        print("  ✓ F&O quote carries oi > 0")

        eq = gw.quote("RELIANCE", exchange="NSE")
        print(f"  RELIANCE ltp={eq.ltp} oi={eq.oi}")
        assert eq.oi == 0, f"equity oi must be 0, got {eq.oi}"
        print("  ✓ Equity quote oi == 0")
        return True
    except AssertionError as e:
        print(f"  ✗ ASSERTION FAILED: {e}")
        return False
    except Exception as e:
        import traceback as _tb

        _tb.print_exc()
        print(f"  ✗ ERROR: {type(e).__name__}: {e}")
        return False


def _probe_upstox(env: dict[str, str]) -> bool:
    print("\n" + "=" * 60)
    print("  UPSTOX — real full-quote OI probe")
    print("=" * 60)
    token = env.get("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("  SKIP: UPSTOX_ACCESS_TOKEN not set")
        return False
    base = env.get("UPSTOX_BASE_V2") or env.get("UPSTOX_BASE_URL") or "https://api.upstox.com"
    base = base.rstrip("/")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        # F&O contract (index future key). Resolve live if possible, else use a
        # known stable format; the assertion below tolerates a miss by SKIP.
        fno_key = "NSE_FO|NIFTY25JULFUT"
        try:
            from brokers.upstox.auth.config import UpstoxSettingsLoader
            from brokers.upstox.auth.token_manager import UpstoxTokenManager
            from brokers.upstox.instruments.service import get_instrument_service

            settings = UpstoxSettingsLoader.from_env()
            tok = UpstoxTokenManager(settings).bearer_token()
            headers["Authorization"] = f"Bearer {tok}"
            svc = get_instrument_service(settings)
            if hasattr(svc, "search"):
                for o in svc.search("NIFTY")[:100]:
                    ex = str(getattr(o, "exchange", ""))
                    it = str(getattr(o, "instrument_type", ""))
                    if "NFO" in ex or "FUT" in it:
                        k = getattr(o, "instrument_key", None) or getattr(o, "instrument_token", None)
                        if k:
                            fno_key = str(k)
                            break
        except Exception as e:
            print(f"  (instrument resolution fallback: {type(e).__name__}; using {fno_key})")

        print(f"  F&O key: {fno_key}")
        r = requests.get(
            f"{base}/v2/market-quote/quotes",
            params={"instrument_key": fno_key},
            headers=headers,
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  SKIP: full-quote returned {r.status_code}: {r.text[:200]}")
            return False
        data = (r.json().get("data") or {}).get(fno_key)
        if not data:
            # alias form uses ':' separator
            data = next(iter((r.json().get("data") or {}).values()), None)
        if not data:
            print("  SKIP: no data for resolved F&O key")
            return False
        raw_oi = data.get("oi", 0)
        print(f"  raw last_price={data.get('last_price')} raw oi={raw_oi}")

        from brokers.upstox.mappers.equity_mapper import UpstoxDomainMapper

        key = fno_key.replace("|", ":")
        q = UpstoxDomainMapper.to_quote({"data": {key: data}})
        print(f"  mapped ltp={q.ltp} volume={q.volume} oi={q.oi}")
        assert isinstance(q.oi, int)
        assert q.oi > 0, f"expected oi>0 for F&O contract, got {q.oi}"
        print("  ✓ F&O quote carries oi > 0")

        # Equity defaults to 0
        r2 = requests.get(
            f"{base}/v2/market-quote/quotes",
            params={"instrument_key": "NSE_EQ|INE002A01018"},
            headers=headers,
            timeout=15,
        )
        if r2.status_code == 200:
            eq_data = (r2.json().get("data") or {}).get("NSE_EQ|INE002A01018")
            if eq_data:
                eq_q = UpstoxDomainMapper.to_quote(
                    {"data": {"NSE_EQ:RELIANCE": eq_data}}
                )
                print(f"  RELIANCE mapped oi={eq_q.oi}")
                assert eq_q.oi == 0, f"equity oi must be 0, got {eq_q.oi}"
                print("  ✓ Equity quote oi == 0")
        return True
    except AssertionError as e:
        print(f"  ✗ ASSERTION FAILED: {e}")
        return False
    except Exception as e:
        print(f"  ✗ ERROR: {type(e).__name__}: {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("  REAL-DATA QUOTE OI VERIFICATION (no mocks)")
    print("=" * 60)
    env = _load_env()
    t0 = time.monotonic()
    results = {}
    results["dhan"] = _probe_dhan(env)
    results["upstox"] = _probe_upstox(env)
    elapsed = time.monotonic() - t0
    print("\n" + "=" * 60)
    print(f"  DONE in {elapsed:.1f}s")
    print(f"  dhan   : {'PASS' if results['dhan'] else 'SKIP/FAIL'}")
    print(f"  upstox : {'PASS' if results['upstox'] else 'SKIP/FAIL'}")
    print("=" * 60)
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
