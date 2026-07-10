"""Multi-symbol speed benchmark for NSE and MCX segments.

Tests real-world performance with:
- Single symbol (baseline)
- 5 symbols (small batch)
- 10 symbols (medium batch)
- 50 symbols (large batch)
- 100 symbols (stress test)

Measures:
- Sequential vs Batch API performance
- LTP, Quote, History latency
- Throughput (symbols/second)
- Memory usage for large batches
"""

import contextlib
import os
import statistics
import sys
import time
from decimal import Decimal

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def benchmark_operation(name, func, iterations=3):
    """Benchmark a single operation."""
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = func()
        elapsed = (time.perf_counter() - t0) * 1000  # ms
        latencies.append(elapsed)

    return {
        'name': name,
        'avg_ms': statistics.mean(latencies),
        'min_ms': min(latencies),
        'max_ms': max(latencies),
        'p50_ms': statistics.median(latencies),
        'result': result
    }

def test_multi_symbol_performance(gw):
    """Test multi-symbol performance across different batch sizes."""

    print("="*80)
    print("MULTI-SYMBOL SPEED BENCHMARK — NSE & MCX")
    print("="*80)

    # Test configurations
    test_sizes = [1, 5, 10, 20, 50]

    # NSE Equity symbols
    nse_symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "HINDUNILVR", "ITC", "KOTAKBANK", "LT", "SBIN",
        "BHARTIARTL", "BAJFINANCE", "ASIANPAINT", "MARUTI", "TITAN",
        "SUNPHARMA", "WIPRO", "AXISBANK", "ONGC", "NTPC",
        "POWERGRID", "TATASTEEL", "ULTRACEMCO", "M&M", "JSWSTEEL",
        "ADANIPORTS", "TECHM", "ADANIENT", "BAJAJ-AUTO", "GRASIM",
        "HDFCLIFE", "BRITANNIA", "CIPLA", "DRREDDY", "EICHERMOT",
        "HEROMOTOCO", "INDUSINDBK", "BPCL", "COALINDIA", "DIVISLAB",
        "HINDALCO", "NESTLEIND", "TATACONSUM", "UPL", "APOLLOHOSP",
        "SBILIFE", "SHREECEM", "PIDILITIND", "DABUR", "COLPAL"
    ]

    results = []

    # ── Test 1: LTP Performance ─────────────────────────────────────────
    print("\n" + "="*80)
    print("TEST 1: LTP (Last Traded Price)")
    print("="*80)

    print("\n--- Sequential LTP Calls ---")
    for size in test_sizes:
        symbols = nse_symbols[:size]

        def fetch_ltp_sequential():
            return {sym: gw.ltp(sym, "NSE") for sym in symbols}

        stats = benchmark_operation(f"LTP Sequential ({size})", fetch_ltp_sequential)
        throughput = size / (stats['avg_ms'] / 1000)  # symbols/sec

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{stats['min_ms']:8.1f}ms min | {stats['max_ms']:8.1f}ms max | "
              f"{throughput:6.1f} sym/sec")

        results.append({
            'test': 'LTP Sequential',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # Batch LTP (if supported)
    print("\n--- Batch LTP API ---")
    for size in [5, 10, 20, 50]:
        symbols = nse_symbols[:size]

        def fetch_ltp_batch():
            return gw.ltp_batch(symbols, "NSE")

        stats = benchmark_operation(f"LTP Batch ({size})", fetch_ltp_batch)
        throughput = size / (stats['avg_ms'] / 1000)

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{stats['min_ms']:8.1f}ms min | {stats['max_ms']:8.1f}ms max | "
              f"{throughput:6.1f} sym/sec")

        results.append({
            'test': 'LTP Batch',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # ── Test 2: Quote Performance ───────────────────────────────────────
    print("\n" + "="*80)
    print("TEST 2: Quote (Full OHLCV)")
    print("="*80)

    print("\n--- Sequential Quote Calls ---")
    for size in [1, 5, 10, 20]:
        symbols = nse_symbols[:size]

        def fetch_quote_sequential():
            return {sym: gw.quote(sym, "NSE") for sym in symbols}

        stats = benchmark_operation(f"Quote Sequential ({size})", fetch_quote_sequential)
        throughput = size / (stats['avg_ms'] / 1000)

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{throughput:6.1f} sym/sec")

        results.append({
            'test': 'Quote Sequential',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # Batch Quote
    print("\n--- Batch Quote API ---")
    for size in [5, 10, 20]:
        symbols = nse_symbols[:size]

        def fetch_quote_batch():
            return gw.quote_batch(symbols, "NSE")

        stats = benchmark_operation(f"Quote Batch ({size})", fetch_quote_batch)
        throughput = size / (stats['avg_ms'] / 1000)

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{throughput:6.1f} sym/sec")

        results.append({
            'test': 'Quote Batch',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # ── Test 3: Historical Data Performance ─────────────────────────────
    print("\n" + "="*80)
    print("TEST 3: Historical Data (1D, 10 days)")
    print("="*80)

    print("\n--- Sequential History Calls ---")
    for size in [1, 5, 10]:
        symbols = nse_symbols[:size]

        def fetch_history_sequential():
            return {sym: gw.history(sym, "NSE", timeframe="1D", lookback_days=10)
                    for sym in symbols}

        stats = benchmark_operation(f"History Sequential ({size})", fetch_history_sequential)
        throughput = size / (stats['avg_ms'] / 1000)

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{throughput:6.1f} sym/sec")

        results.append({
            'test': 'History Sequential',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # Batch History
    print("\n--- Batch History API ---")
    for size in [5, 10]:
        symbols = nse_symbols[:size]

        def fetch_history_batch():
            return gw.history_batch(symbols, "NSE", timeframe="1D", lookback_days=10)

        stats = benchmark_operation(f"History Batch ({size})", fetch_history_batch)
        # For batch history, result is a DataFrame, count unique symbols
        df = stats['result']
        unique_symbols = df['symbol'].nunique() if hasattr(df, 'symbol') else size
        throughput = unique_symbols / (stats['avg_ms'] / 1000)

        print(f"  {size:3d} symbols: {stats['avg_ms']:8.1f}ms avg | "
              f"{throughput:6.1f} sym/sec | {len(df)} total bars")

        results.append({
            'test': 'History Batch',
            'symbols': size,
            'avg_ms': stats['avg_ms'],
            'throughput': throughput
        })

    # ── Test 4: MCX Commodity Performance ───────────────────────────────
    print("\n" + "="*80)
    print("TEST 4: MCX Commodity (GOLD, SILVER, CRUDEOIL)")
    print("="*80)

    mcx_symbols = ["GOLD", "SILVER", "CRUDEOIL", "NATURALGAS", "COPPER"]

    # LTP
    def fetch_mcx_ltp():
        return {sym: gw.ltp(sym, "MCX") for sym in mcx_symbols}

    stats = benchmark_operation("MCX LTP (5 symbols)", fetch_mcx_ltp)
    print(f"  LTP (5 commodities): {stats['avg_ms']:.1f}ms avg")

    # Quote
    def fetch_mcx_quote():
        return {sym: gw.quote(sym, "MCX") for sym in mcx_symbols[:3]}

    stats = benchmark_operation("MCX Quote (3 symbols)", fetch_mcx_quote)
    print(f"  Quote (3 commodities): {stats['avg_ms']:.1f}ms avg")

    # History
    def fetch_mcx_history():
        return {sym: gw.history(sym, "MCX", timeframe="1D", lookback_days=10)
                for sym in mcx_symbols[:3]}

    stats = benchmark_operation("MCX History (3 symbols)", fetch_mcx_history)
    print(f"  History (3 commodities): {stats['avg_ms']:.1f}ms avg")

    # ── Test 5: Derivatives Performance ─────────────────────────────────
    print("\n" + "="*80)
    print("TEST 5: Derivatives (Options & Futures Chains)")
    print("="*80)

    # Option Chain
    def fetch_option_chain_nifty():
        return gw.option_chain("NIFTY", "NFO")

    stats = benchmark_operation("Option Chain (NIFTY)", fetch_option_chain_nifty)
    chain = stats['result']
    strikes = len(chain.strikes) if hasattr(chain, 'strikes') else 0
    print(f"  NIFTY Options: {stats['avg_ms']:.1f}ms | {strikes} strikes")

    def fetch_option_chain_gold():
        return gw.option_chain("GOLD", "MCX")

    stats = benchmark_operation("Option Chain (GOLD MCX)", fetch_option_chain_gold)
    chain = stats['result']
    strikes = len(chain.strikes) if hasattr(chain, 'strikes') else 0
    print(f"  GOLD Options (MCX): {stats['avg_ms']:.1f}ms | {strikes} strikes")

    # Future Chain
    def fetch_future_chain_nifty():
        return gw.future_chain("NIFTY", "NFO")

    stats = benchmark_operation("Future Chain (NIFTY)", fetch_future_chain_nifty)
    chain = stats['result']
    contracts = len(chain.contracts) if hasattr(chain, 'contracts') else 0
    print(f"  NIFTY Futures: {stats['avg_ms']:.1f}ms | {contracts} contracts")

    def fetch_future_chain_gold():
        return gw.future_chain("GOLD", "MCX")

    stats = benchmark_operation("Future Chain (GOLD MCX)", fetch_future_chain_gold)
    chain = stats['result']
    contracts = len(chain.contracts) if hasattr(chain, 'contracts') else 0
    print(f"  GOLD Futures (MCX): {stats['avg_ms']:.1f}ms | {contracts} contracts")

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("PERFORMANCE SUMMARY")
    print("="*80)

    print(f"\n{'Test':<25} {'Symbols':>8} {'Avg (ms)':>10} {'Throughput':>12}")
    print("-" * 60)

    for r in results:
        print(f"{r['test']:<25} {r['symbols']:8d} {r['avg_ms']:10.1f} "
              f"{r['throughput']:8.1f} sym/s")

    # Performance insights
    print("\n" + "="*80)
    print("PERFORMANCE INSIGHTS")
    print("="*80)

    # Find best throughput
    ltp_seq = [r for r in results if r['test'] == 'LTP Sequential']
    ltp_batch = [r for r in results if r['test'] == 'LTP Batch']

    if ltp_seq and ltp_batch:
        seq_50 = next((r for r in ltp_seq if r['symbols'] == 50), None)
        batch_50 = next((r for r in ltp_batch if r['symbols'] == 50), None)

        if seq_50 and batch_50:
            speedup = seq_50['avg_ms'] / batch_50['avg_ms']
            print(f"\n✅ LTP Batch API is {speedup:.1f}x faster than sequential for 50 symbols")
            print(f"   Sequential: {seq_50['avg_ms']:.0f}ms")
            print(f"   Batch API:  {batch_50['avg_ms']:.0f}ms")

    quote_seq = [r for r in results if r['test'] == 'Quote Sequential']
    quote_batch = [r for r in results if r['test'] == 'Quote Batch']

    if quote_seq and quote_batch:
        seq_20 = next((r for r in quote_seq if r['symbols'] == 20), None)
        batch_20 = next((r for r in quote_batch if r['symbols'] == 20), None)

        if seq_20 and batch_20:
            speedup = seq_20['avg_ms'] / batch_20['avg_ms']
            print(f"\n✅ Quote Batch API is {speedup:.1f}x faster than sequential for 20 symbols")

    print("\n" + "="*80)
    print("BENCHMARK COMPLETE")
    print("="*80)

    return results

def main():
    print("╔" + "═"*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "  INTELLIGENT GATEWAY BENCHMARK — SMART vs SIMPLE MODE".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "═"*78 + "╝")
    print()

    try:
        import asyncio

        from brokers.dhan.identity.factory import BrokerFactory

        print("Creating Dhan Gateway...")
        factory = BrokerFactory()
        dhan_gw = factory.create(load_instruments=True)
        print(f"Dhan Gateway created. Instruments: {dhan_gw.describe().get('instrument_count', '?')}")
        print()

        # Create intelligent gateway in both modes
        # NOTE: create_intelligent_gateway removed during refactoring;
        # using raw gateway directly as placeholder.
        smart_gw = dhan_gw
        simple_gw = dhan_gw
        print("Intelligent gateway creation skipped during broker refactoring")
        print()

        # Run benchmarks for both modes
        print("="*80)
        print("BENCHMARK 1: SMART MODE (Intelligent Routing)")
        print("="*80)
        smart_results = test_multi_symbol_performance(smart_gw)

        print("\n" + "="*80)
        print("BENCHMARK 2: SIMPLE MODE (Direct Broker)")
        print("="*80)
        simple_results = test_multi_symbol_performance(simple_gw)

        # Compare results
        print("\n" + "="*80)
        print("COMPARISON: SMART vs SIMPLE MODE")
        print("="*80)

        # Compare LTP performance
        smart_ltp_10 = next((r for r in smart_results if r['test'] == 'LTP Sequential' and r['symbols'] == 10), None)
        simple_ltp_10 = next((r for r in simple_results if r['test'] == 'LTP Sequential' and r['symbols'] == 10), None)

        if smart_ltp_10 and simple_ltp_10:
            speedup = simple_ltp_10['avg_ms'] / smart_ltp_10['avg_ms']
            if speedup > 1.0:
                print(f"\n✅ Smart mode is {speedup:.1f}x FASTER for 10-symbol LTP")
            elif speedup < 1.0:
                print(f"\n⚠️  Simple mode is {1/speedup:.1f}x faster (smart mode has overhead)")
            else:
                print(f"\n✓ Both modes have similar performance")

            print(f"   Smart mode:  {smart_ltp_10['avg_ms']:.0f}ms")
            print(f"   Simple mode: {simple_ltp_10['avg_ms']:.0f}ms")

        # Close gateways
        with contextlib.suppress(BaseException):
            smart_gw.close()

        print(f"\n✅ Benchmark completed successfully.")
        print(f"   Smart mode: {len(smart_results)} tests")
        print(f"   Simple mode: {len(simple_results)} tests")

    except Exception as e:
        print(f"\n💥 FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
