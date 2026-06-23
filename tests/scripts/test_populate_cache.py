#!/usr/bin/env python
"""Populate Dhan instrument cache and test speed."""

import time
from pathlib import Path

from brokers.common.instrument_cache import InstrumentCacheManager
from brokers.dhan.instruments.cache_adapter import DhanInstrumentAdapter

print("=" * 80)
print("Populating Dhan Instrument Cache")
print("=" * 80)

# Initialize cache
cache_db = Path(".cache/instruments.db")
cache_mgr = InstrumentCacheManager(db_path=cache_db)
adapter = DhanInstrumentAdapter(db_path=cache_db)
cache_mgr.register_adapter(adapter)

print("\nLoading instruments from CSV...")
start = time.time()

from brokers.dhan.instruments.loader import InstrumentLoader

rows = InstrumentLoader.load_cached()
load_time = time.time() - start
print(f"  ✅ Loaded {len(rows):,} instruments in {load_time:.3f}s")

print("\nConverting to Instrument objects...")
start = time.time()
from brokers.dhan.domain import Instrument

instruments = []
for row in rows:
    try:
        inst = Instrument(
            symbol=row.get("symbol", ""),
            exchange=row.get("exchange"),
            security_id=row.get("security_id", ""),
            instrument_type=row.get("instrument_type"),
            expiry=row.get("expiry"),
            strike_price=row.get("strike_price"),
            option_type=row.get("option_type"),
            underlying=row.get("underlying"),
            lot_size=row.get("lot_size", 1),
            tick_size=row.get("tick_size", 0.05),
            canonical_symbol=row.get("canonical_symbol"),
            sm_symbol_name=row.get("sm_symbol_name"),
        )
        instruments.append(inst)
    except Exception:
        continue

convert_time = time.time() - start
print(f"  ✅ Converted {len(instruments):,} instruments in {convert_time:.3f}s")

print("\nCaching to SQLite...")
start = time.time()
cache_mgr.cache_instruments("dhan", instruments)
cache_time = time.time() - start
print(f"  ✅ Cached in {cache_time:.3f}s")

# Verify
count = cache_mgr.get_instrument_count("dhan")
print(f"\n✅ Total instruments in cache: {count:,}")

# Check cache is valid
is_valid = cache_mgr.is_cache_valid("dhan")
print(f"✅ Cache valid: {is_valid}")

print("\n" + "=" * 80)
print("Performance Summary")
print("=" * 80)
print(f"  CSV load:        {load_time:.3f}s")
print(f"  Convert:         {convert_time:.3f}s")
print(f"  SQLite insert:   {cache_time:.3f}s")
print(f"  Total:           {load_time + convert_time + cache_time:.3f}s")
print(f"  Speed per instrument: {(load_time + convert_time + cache_time) / len(instruments) * 1000:.3f}ms")
print("=" * 80)
