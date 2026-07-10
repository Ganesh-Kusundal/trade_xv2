#!/usr/bin/env python
"""Test CLI speed with SQLite instrument cache."""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 80)
print("CLI Speed Test: SQLite Instrument Cache")
print("=" * 80)

# Test 1: Import speed
print("\n[1/4] Testing import speed...")
start = time.time()
from interface.ui.services.broker_service import BrokerService

import_time = time.time() - start
print(f"  ✅ Import time: {import_time:.3f}s")

# Test 2: Broker service initialization
print("\n[2/4] Testing broker service initialization...")
start = time.time()
service = BrokerService()
service.initialize()
init_time = time.time() - start
print(f"  ✅ Initialization time: {init_time:.3f}s")

# Test 3: First quote (warm cache)
print("\n[3/4] Testing first quote (warm cache)...")
start = time.time()
try:
    gw = service.active_broker
    quote = gw.quote("RELIANCE", "NSE")
    quote_time = time.time() - start
    print(f"  ✅ Quote time: {quote_time:.3f}s")
    print(f"  ✅ RELIANCE LTP: ₹{quote.ltp:,.2f}")
except Exception as e:
    quote_time = time.time() - start
    print(f"  ⚠️  Quote failed (expected if no live connection): {e}")
    print(f"  ⏱️  Attempt time: {quote_time:.3f}s")

# Test 4: Cache statistics
print("\n[4/4] Checking cache statistics...")
try:
    # Check if cache exists
    cache_db = Path(".cache/instruments.db")
    if cache_db.exists():
        db_size = cache_db.stat().st_size
        print(f"  ✅ Cache database exists: {cache_db}")
        print(f"  ✅ Database size: {db_size / 1024:.1f} KB")

        # Check cache metadata
        import sqlite3

        conn = sqlite3.connect(str(cache_db))
        cursor = conn.execute("SELECT broker, cached_at, instrument_count FROM cache_metadata")
        for row in cursor.fetchall():
            print(f"  ✅ {row[0]}: {row[2]:,} instruments cached at {row[1]}")
        conn.close()
    else:
        print(f"  ⚠️  Cache database not found at {cache_db}")
except Exception as e:
    print(f"  ⚠️  Cache check failed: {e}")

# Summary
print("\n" + "=" * 80)
print("Summary")
print("=" * 80)
print(f"  Import time:           {import_time:.3f}s")
print(f"  Initialization time:   {init_time:.3f}s")
print(f"  First quote time:      {quote_time:.3f}s")
print(f"  Total time:            {import_time + init_time + quote_time:.3f}s")
print("=" * 80)
