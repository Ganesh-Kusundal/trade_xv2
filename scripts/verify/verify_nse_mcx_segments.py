"""Comprehensive NSE and MCX segment verification script.

Tests all market data endpoints across:
- NSE Equity (NSE)
- NSE Futures & Options (NFO)    # noqa: W291
- NSE Index (IDX_I)
- MCX Commodity (MCX)
- MCX Commodity Options (MCX)
"""

import contextlib
import os
import sys
import time
from datetime import date
from decimal import Decimal

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️"

results = []

def record(test: str, segment: str, status: str, detail: str = ""):
    results.append((test, segment, status, detail))
    icon = {"PASS": PASS, "FAIL": FAIL, "SKIP": SKIP}[status]
    print(f"  {icon} {test:30s} [{segment:15s}] {detail[:80]}")

def test_nse_equity(gw):
    """Test NSE Equity segment."""
    print("\n" + "="*70)
    print("NSE EQUITY (NSE)")
    print("="*70)

    symbol = "RELIANCE"

    # LTP
    try:
        ltp = gw.ltp(symbol, "NSE")
        record("LTP", "NSE", "PASS" if ltp and ltp > 0 else "FAIL", f"{symbol} = {ltp}")
    except Exception as e:
        record("LTP", "NSE", "FAIL", str(e))
    time.sleep(0.2)

    # Quote
    try:
        quote = gw.quote(symbol, "NSE")
        record("Quote", "NSE", "PASS" if quote and quote.ltp else "FAIL",
               f"LTP={quote.ltp}, Vol={quote.volume}")
    except Exception as e:
        record("Quote", "NSE", "FAIL", str(e))
    time.sleep(0.2)

    # Depth
    try:
        depth = gw.depth(symbol, "NSE")
        bids = len(depth.bids) if depth and hasattr(depth, 'bids') else 0
        asks = len(depth.asks) if depth and hasattr(depth, 'asks') else 0
        record("Depth (5-level)", "NSE", "PASS" if bids > 0 else "FAIL",
               f"{bids} bids, {asks} asks")
    except Exception as e:
        record("Depth (5-level)", "NSE", "FAIL", str(e))
    time.sleep(0.2)

    # History Daily
    try:
        df = gw.history(symbol, "NSE", timeframe="1D", lookback_days=10)
        record("History (1D)", "NSE", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df) if df is not None else 0} bars")
    except Exception as e:
        record("History (1D)", "NSE", "FAIL", str(e))
    time.sleep(0.3)

    # History Intraday
    try:
        df = gw.history(symbol, "NSE", timeframe="5m", lookback_days=5)
        record("History (5m)", "NSE", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df) if df is not None else 0} bars")
    except Exception as e:
        record("History (5m)", "NSE", "FAIL", str(e))
    time.sleep(0.3)

def test_nse_fno(gw):
    """Test NSE F&O segment (NFO)."""
    print("\n" + "="*70)
    print("NSE FUTURES & OPTIONS (NFO)")
    print("="*70)

    # Future Chain
    try:
        chain = gw.future_chain("NIFTY", "NFO")
        contracts = len(chain.contracts) if chain and hasattr(chain, 'contracts') else 0
        expiries = len(chain.expiries) if chain and hasattr(chain, 'expiries') else 0
        record("Future Chain", "NFO", "PASS" if contracts > 0 else "FAIL",
               f"{contracts} contracts, {expiries} expiries")
    except Exception as e:
        record("Future Chain", "NFO", "FAIL", str(e))
    time.sleep(0.3)

    # Option Chain
    try:
        chain = gw.option_chain("NIFTY", "NFO")
        strikes = len(chain.strikes) if chain and hasattr(chain, 'strikes') else 0
        record("Option Chain", "NFO", "PASS" if strikes > 0 else "FAIL",
               f"{strikes} strikes")
    except Exception as e:
        record("Option Chain", "NFO", "FAIL", str(e))
    time.sleep(0.3)

    # History for Index
    try:
        df = gw.history("NIFTY", "IDX_I", timeframe="1D", lookback_days=10)
        record("History Index (1D)", "IDX_I", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df) if df is not None else 0} bars")
    except Exception as e:
        record("History Index (1D)", "IDX_I", "FAIL", str(e))
    time.sleep(0.3)

def test_mcx_commodity(gw):
    """Test MCX Commodity segment."""
    print("\n" + "="*70)
    print("MCX COMMODITY (MCX)")
    print("="*70)

    symbol = "GOLD"

    # LTP
    try:
        ltp = gw.ltp(symbol, "MCX")
        record("LTP", "MCX", "PASS" if ltp and ltp > 0 else "FAIL", f"{symbol} = {ltp}")
    except Exception as e:
        record("LTP", "MCX", "FAIL", str(e))
    time.sleep(0.2)

    # Quote
    try:
        quote = gw.quote(symbol, "MCX")
        record("Quote", "MCX", "PASS" if quote and quote.ltp else "FAIL",
               f"LTP={quote.ltp}")
    except Exception as e:
        record("Quote", "MCX", "FAIL", str(e))
    time.sleep(0.2)

    # Depth
    try:
        depth = gw.depth(symbol, "MCX")
        bids = len(depth.bids) if depth and hasattr(depth, 'bids') else 0
        asks = len(depth.asks) if depth and hasattr(depth, 'asks') else 0
        record("Depth (5-level)", "MCX", "PASS" if bids > 0 else "FAIL",
               f"{bids} bids, {asks} asks")
    except Exception as e:
        record("Depth (5-level)", "MCX", "FAIL", str(e))
    time.sleep(0.2)

    # History Daily
    try:
        df = gw.history(symbol, "MCX", timeframe="1D", lookback_days=10)
        record("History (1D)", "MCX", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df) if df is not None else 0} bars")
    except Exception as e:
        record("History (1D)", "MCX", "FAIL", str(e))
    time.sleep(0.3)

    # History Intraday
    try:
        df = gw.history(symbol, "MCX", timeframe="5m", lookback_days=5)
        record("History (5m)", "MCX", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df) if df is not None else 0} bars")
    except Exception as e:
        record("History (5m)", "MCX", "FAIL", str(e))
    time.sleep(0.3)

    # Future Chain
    try:
        chain = gw.future_chain(symbol, "MCX")
        contracts = len(chain.contracts) if chain and hasattr(chain, 'contracts') else 0
        expiries = len(chain.expiries) if chain and hasattr(chain, 'expiries') else 0
        record("Future Chain", "MCX", "PASS" if contracts > 0 else "FAIL",
               f"{contracts} contracts, {expiries} expiries")
    except Exception as e:
        record("Future Chain", "MCX", "FAIL", str(e))
    time.sleep(0.3)

    # Option Chain
    try:
        chain = gw.option_chain(symbol, "MCX")
        strikes = len(chain.strikes) if chain and hasattr(chain, 'strikes') else 0
        record("Option Chain", "MCX", "PASS" if strikes > 0 else "FAIL",
               f"{strikes} strikes")
    except Exception as e:
        record("Option Chain", "MCX", "FAIL", str(e))
    time.sleep(0.3)

    # Test SILVER
    try:
        ltp = gw.ltp("SILVER", "MCX")
        record("LTP (SILVER)", "MCX", "PASS" if ltp and ltp > 0 else "FAIL", f"SILVER = {ltp}")
    except Exception as e:
        record("LTP (SILVER)", "MCX", "FAIL", str(e))
    time.sleep(0.2)

    # Test CRUDEOIL
    try:
        ltp = gw.ltp("CRUDEOIL", "MCX")
        record("LTP (CRUDEOIL)", "MCX", "PASS" if ltp and ltp > 0 else "FAIL", f"CRUDEOIL = {ltp}")
    except Exception as e:
        record("LTP (CRUDEOIL)", "MCX", "FAIL", str(e))
    time.sleep(0.2)

def test_batch_operations(gw):
    """Test batch operations."""
    print("\n" + "="*70)
    print("BATCH OPERATIONS")
    print("="*70)

    # LTP Batch NSE
    try:
        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
        batch = gw.ltp_batch(symbols, "NSE")
        record("LTP Batch", "NSE", "PASS" if batch and len(batch) > 0 else "FAIL",
               f"{len(batch)} symbols")
    except Exception as e:
        record("LTP Batch", "NSE", "FAIL", str(e))
    time.sleep(0.3)

    # Quote Batch NSE
    try:
        symbols = ["RELIANCE", "TCS", "INFY"]
        batch = gw.quote_batch(symbols, "NSE")
        record("Quote Batch", "NSE", "PASS" if batch and len(batch) > 0 else "FAIL",
               f"{len(batch)} symbols")
    except Exception as e:
        record("Quote Batch", "NSE", "FAIL", str(e))
    time.sleep(0.3)

    # History Batch NSE
    try:
        symbols = ["RELIANCE", "TCS"]
        df = gw.history_batch(symbols, "NSE", timeframe="1D", lookback_days=5)
        record("History Batch", "NSE", "PASS" if df is not None and len(df) > 0 else "FAIL",
               f"{len(df)} bars")
    except Exception as e:
        record("History Batch", "NSE", "FAIL", str(e))

def main():
    print("╔" + "═"*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  COMPREHENSIVE NSE & MCX SEGMENT VERIFICATION".center(68) + "║")
    print("║" + " "*68 + "║")
    print("║" + "  Tests: NSE Equity, NSE F&O, NSE Index, MCX Commodity".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "═"*68 + "╝")
    print()

    try:
        _root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(_root / "src"))
        sys.path.insert(0, str(_root / "scripts"))
        from _connect import bootstrap_or_exit

        print("Creating Dhan Gateway...")
        gw = bootstrap_or_exit("dhan", load_instruments=True)
        print(f"Gateway created. Instruments: {gw.describe().get('instrument_count', '?')}")

        # Run all tests
        test_nse_equity(gw)
        test_nse_fno(gw)
        test_mcx_commodity(gw)
        test_batch_operations(gw)

        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)

        passed = sum(1 for r in results if r[2] == "PASS")
        failed = sum(1 for r in results if r[2] == "FAIL")
        skipped = sum(1 for r in results if r[2] == "SKIP")
        total = len(results)

        print(f"\nTotal: {total}  |  {PASS} PASS: {passed}  |  {FAIL} FAIL: {failed}  |  {SKIP} SKIP: {skipped}")
        print()

        if failed:
            print("FAILURES:")
            for test, segment, status, detail in results:
                if status == "FAIL":
                    print(f"  {FAIL} {test:30s} [{segment}] {detail[:100]}")
            print()

        print(f"Result: {'✅ ALL TESTS PASSED' if failed == 0 else f'❌ {failed} FAILURES'}")

        # Close gateway
        with contextlib.suppress(BaseException):
            gw._conn.close()

    except Exception as e:
        print(f"\n💥 FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
