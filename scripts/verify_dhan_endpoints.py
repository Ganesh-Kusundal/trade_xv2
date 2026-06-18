"""Dhan data retrieval endpoint verification across all segments.

Tests every gateway data endpoint for NSE, BSE, NFO, MCX, CDS, and INDEX.
"""
import sys
import os
import time
import traceback
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: list[tuple[str, str, str, str]] = []  # (endpoint, segment, status, detail)


def record(endpoint: str, segment: str, status: str, detail: str = ""):
    results.append((endpoint, segment, status, detail))
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}[status]
    print(f"  {icon} {endpoint:25s} [{segment:12s}] {detail[:80]}")


def test_gateway():
    from brokers.dhan.factory import BrokerFactory

    print("=== Creating Dhan Gateway ===")
    factory = BrokerFactory()
    gw = factory.create(load_instruments=True)
    print(f"Gateway created. Instruments loaded: {gw.describe().get('instrument_count', '?')}")
    print()

    # ── 1. LTP across segments ──────────────────────────────────────────
    print("=== LTP (single) ===")
    ltp_tests = [
        ("RELIANCE", "NSE", "NSE Equity"),
        ("RELIANCE", "BSE", "BSE Equity"),
        ("NIFTY", "IDX_I", "NSE Index"),
        ("USDINR", "CDS", "Currency"),
    ]
    for symbol, exchange, label in ltp_tests:
        try:
            val = gw.ltp(symbol, exchange)
            if val and val > 0:
                record("ltp", f"{exchange}({label})", PASS, f"{symbol} = {val}")
            else:
                record("ltp", f"{exchange}({label})", FAIL, f"got {val}")
        except Exception as e:
            record("ltp", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.2)

    # MCX LTP
    try:
        val = gw.ltp("GOLD", "MCX")
        if val and val > 0:
            record("ltp", "MCX(Commodity)", PASS, f"GOLD = {val}")
        else:
            record("ltp", "MCX(Commodity)", FAIL, f"got {val}")
    except Exception as e:
        record("ltp", "MCX(Commodity)", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    # NFO LTP (option)
    try:
        val = gw.ltp("NIFTY", "NFO")
        record("ltp", "NFO(F&O)", PASS, f"NIFTY = {val}" if val else "returned None/0")
    except Exception as e:
        record("ltp", "NFO(F&O)", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    # ── 2. Quote across segments ────────────────────────────────────────
    print("\n=== Quote (single) ===")
    quote_tests = [
        ("RELIANCE", "NSE", "NSE Equity"),
        ("RELIANCE", "BSE", "BSE Equity"),
        ("NIFTY", "IDX_I", "NSE Index"),
    ]
    for symbol, exchange, label in quote_tests:
        try:
            q = gw.quote(symbol, exchange)
            if q and q.ltp and q.ltp > 0:
                record("quote", f"{exchange}({label})", PASS, f"{symbol} LTP={q.ltp}, OHLC=({q.open},{q.high},{q.low},{q.close})")
            else:
                record("quote", f"{exchange}({label})", FAIL, f"got {q}")
        except Exception as e:
            record("quote", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.2)

    # ── 3. Depth across segments ────────────────────────────────────────
    print("\n=== Depth (5-level REST) ===")
    depth_tests = [
        ("RELIANCE", "NSE", "NSE Equity"),
        ("RELIANCE", "BSE", "BSE Equity"),
    ]
    for symbol, exchange, label in depth_tests:
        try:
            d = gw.depth(symbol, exchange)
            if d:
                buy_count = len(d.bids) if hasattr(d, 'bids') else 0
                sell_count = len(d.asks) if hasattr(d, 'asks') else 0
                record("depth", f"{exchange}({label})", PASS, f"bids={buy_count}, asks={sell_count}")
            else:
                record("depth", f"{exchange}({label})", FAIL, "returned None")
        except Exception as e:
            record("depth", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.2)

    # ── 4. Historical data across segments ──────────────────────────────
    print("\n=== Historical Data ===")
    hist_tests = [
        ("RELIANCE", "NSE", "1D", "NSE Equity Daily"),
        ("RELIANCE", "NSE", "5m", "NSE Equity 5min"),
        ("RELIANCE", "BSE", "1D", "BSE Equity Daily"),
        ("NIFTY", "IDX_I", "1D", "Index Daily"),
    ]
    for symbol, exchange, tf, label in hist_tests:
        try:
            df = gw.history(symbol, exchange, timeframe=tf, lookback_days=10)
            if df is not None and len(df) > 0:
                record("history", f"{exchange}({label})", PASS, f"{len(df)} bars, cols={list(df.columns[:5])}")
            else:
                record("history", f"{exchange}({label})", FAIL, f"empty or None ({len(df) if df is not None else 'None'})")
        except Exception as e:
            record("history", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.3)

    # ── 5. Option chain ─────────────────────────────────────────────────
    print("\n=== Option Chain ===")
    for underlying, exchange, label in [("NIFTY", "NFO", "NFO NIFTY"), ("SENSEX", "BFO", "BFO SENSEX")]:
        try:
            chain = gw.option_chain(underlying, exchange)
            if chain and isinstance(chain, dict):
                data = chain.get("data", chain.get("contracts", []))
                count = len(data) if isinstance(data, list) else len(data) if data else 0
                record("option_chain", f"{exchange}({label})", PASS, f"underlying={underlying}, contracts={count}")
            else:
                record("option_chain", f"{exchange}({label})", FAIL, f"got {type(chain)}")
        except Exception as e:
            record("option_chain", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.3)

    # MCX option chain
    try:
        chain = gw.option_chain("GOLD", "MCX")
        if chain and isinstance(chain, dict):
            record("option_chain", "MCX(GOLD)", PASS, f"got chain data")
        else:
            record("option_chain", "MCX(GOLD)", FAIL, f"got {type(chain)}")
    except Exception as e:
        record("option_chain", "MCX(GOLD)", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.3)

    # ── 6. Future chain ─────────────────────────────────────────────────
    print("\n=== Future Chain ===")
    for underlying, exchange, label in [("NIFTY", "NFO", "NFO NIFTY"), ("GOLD", "MCX", "MCX GOLD")]:
        try:
            chain = gw.future_chain(underlying, exchange)
            if chain and isinstance(chain, dict):
                contracts = chain.get("contracts", [])
                expiries = chain.get("expiries", [])
                record("future_chain", f"{exchange}({label})", PASS, f"contracts={len(contracts)}, expiries={len(expiries)}")
            else:
                record("future_chain", f"{exchange}({label})", FAIL, f"got {type(chain)}")
        except Exception as e:
            record("future_chain", f"{exchange}({label})", FAIL, f"{type(e).__name__}: {e}")
        time.sleep(0.3)

    # ── 7. Batch operations ─────────────────────────────────────────────
    print("\n=== Batch Operations ===")
    try:
        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
        batch = gw.ltp_batch(symbols, "NSE")
        if batch and len(batch) > 0:
            record("ltp_batch", "NSE(Equity)", PASS, f"{len(batch)} symbols: {list(batch.keys())[:3]}...")
        else:
            record("ltp_batch", "NSE(Equity)", FAIL, f"got {batch}")
    except Exception as e:
        record("ltp_batch", "NSE(Equity)", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.3)

    try:
        symbols = ["RELIANCE", "TCS", "INFY"]
        batch = gw.quote_batch(symbols, "NSE")
        if batch and len(batch) > 0:
            record("quote_batch", "NSE(Equity)", PASS, f"{len(batch)} symbols returned")
        else:
            record("quote_batch", "NSE(Equity)", FAIL, f"got {batch}")
    except Exception as e:
        record("quote_batch", "NSE(Equity)", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.3)

    # ── 8. Portfolio endpoints ──────────────────────────────────────────
    print("\n=== Portfolio Endpoints ===")
    try:
        bal = gw.funds()
        if bal:
            record("funds", "Account", PASS, f"available={bal.available if hasattr(bal, 'available') else bal}")
        else:
            record("funds", "Account", FAIL, "returned None/empty")
    except Exception as e:
        record("funds", "Account", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    try:
        pos = gw.positions()
        record("positions", "Account", PASS, f"{len(pos)} positions")
    except Exception as e:
        record("positions", "Account", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    try:
        hol = gw.holdings()
        record("holdings", "Account", PASS, f"{len(hol)} holdings")
    except Exception as e:
        record("holdings", "Account", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    try:
        orders = gw.get_orderbook()
        record("orderbook", "Account", PASS, f"{len(orders)} orders")
    except Exception as e:
        record("orderbook", "Account", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    try:
        trades = gw.get_trade_book()
        record("tradebook", "Account", PASS, f"{len(trades)} trades")
    except Exception as e:
        record("tradebook", "Account", FAIL, f"{type(e).__name__}: {e}")
    time.sleep(0.2)

    # ── 9. History batch (parallel) ─────────────────────────────────────
    print("\n=== History Batch (Parallel) ===")
    try:
        symbols = ["RELIANCE", "TCS"]
        df = gw.history_batch(symbols, "NSE", timeframe="1D", lookback_days=5)
        if df is not None and len(df) > 0:
            record("history_batch", "NSE(Equity)", PASS, f"{len(df)} total bars for {len(symbols)} symbols")
        else:
            record("history_batch", "NSE(Equity)", FAIL, f"empty or None")
    except Exception as e:
        record("history_batch", "NSE(Equity)", FAIL, f"{type(e).__name__}: {e}")

    return gw


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     DHAN DATA RETRIEVAL ENDPOINT VERIFICATION               ║")
    print("║     All Segments: NSE, BSE, NFO, BFO, MCX, CDS, INDEX      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    try:
        gw = test_gateway()
    except Exception as e:
        print(f"\n💥 FATAL: Gateway creation failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        try:
            gw._conn.close()
        except Exception:
            pass

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r[2] == PASS)
    failed = sum(1 for r in results if r[2] == FAIL)
    skipped = sum(1 for r in results if r[2] == SKIP)
    total = len(results)
    print(f"  Total: {total}  |  PASS: {passed}  |  FAIL: {failed}  |  SKIP: {skipped}")
    print()

    if failed:
        print("FAILURES:")
        for endpoint, segment, status, detail in results:
            if status == FAIL:
                print(f"  ❌ {endpoint:25s} [{segment}] {detail[:100]}")

    print(f"\nResult: {'ALL PASS' if failed == 0 else f'{failed} FAILURES'}")
