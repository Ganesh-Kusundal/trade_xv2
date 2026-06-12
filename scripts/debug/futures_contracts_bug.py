#!/usr/bin/env python3
"""Debug script to reproduce the 'No contracts found' bug for NIFTY futures."""

import sys
import traceback
from pathlib import Path

# ── Step 1: Create DhanBroker from .env.local ──────────────────────────────
print("=" * 70)
print("STEP 1: Creating DhanBroker from .env.local")
print("=" * 70)

try:
    from brokers.dhan import DhanBroker

    broker = DhanBroker.from_env(env_path=Path(".env.local"))
    print(f"[OK] DhanBroker created — client_id={broker.client_id}")
except Exception:
    print("[FAIL] Could not create DhanBroker:")
    traceback.print_exc()
    sys.exit(1)

# ── Step 2: Check resolver state BEFORE loading catalog ────────────────────
print()
print("=" * 70)
print("STEP 2: Check resolver state BEFORE catalog load")
print("=" * 70)

resolver = broker.instrument_resolver
print(f"  resolver type           : {type(resolver).__name__}")
print(f"  resolver.is_loaded      : {resolver.is_loaded}")
print(f"  resolver.size()         : {resolver.size()}")
print(f"  _futures_by_underlying  : {len(resolver._futures_by_underlying)} entries")
print(f"  _options_by_underlying  : {len(resolver._options_by_underlying)} entries")

# ── Step 3: Try futures_contracts("NIFTY") on empty catalog ────────────────
print()
print("=" * 70)
print("STEP 3: futures_contracts('NIFTY') on EMPTY catalog (the bug)")
print("=" * 70)

try:
    contracts = resolver.futures_contracts("NIFTY")
    print(f"  Result: {len(contracts)} contracts")
    if contracts:
        for c in contracts:
            print(
                f"    - {c.canonical_symbol}  sid={c.security_id}  expiry={c.expiry}  underlying={c.underlying!r}"
            )
    else:
        print("  >>> BUG REPRODUCED: empty list — CLI shows 'No contracts found'")
except Exception:
    print("[ERROR]")
    traceback.print_exc()

# ── Step 4: Load the instrument catalog from Dhan ─────────────────────────
print()
print("=" * 70)
print("STEP 4: Loading instrument catalog (download from Dhan if needed)")
print("=" * 70)

try:
    cache_dir = Path(".cache/instruments")
    resolver.load_from_daily_cache(cache_dir)
    print(f"[OK] Catalog loaded")
    print(f"  resolver.is_loaded      : {resolver.is_loaded}")
    print(f"  resolver.size()         : {resolver.size()}")
    print(f"  _futures_by_underlying  : {len(resolver._futures_by_underlying)} entries")
    print(f"  _options_by_underlying  : {len(resolver._options_by_underlying)} entries")
except Exception:
    print("[FAIL] Could not load catalog:")
    traceback.print_exc()

# ── Step 5: Try futures_contracts("NIFTY") AFTER loading catalog ──────────
print()
print("=" * 70)
print("STEP 5: futures_contracts('NIFTY') AFTER catalog load")
print("=" * 70)

try:
    contracts = resolver.futures_contracts("NIFTY")
    print(f"  Result: {len(contracts)} contracts")
    if contracts:
        for c in contracts:
            print(
                f"    - {c.canonical_symbol}  sid={c.security_id}  "
                f"seg={c.exchange_segment.value}  expiry={c.expiry}  "
                f"underlying={c.underlying!r}  lot={c.lot_size}  "
                f"instr_type={c.instrument_type}"
            )
    else:
        print("  >>> STILL EMPTY after catalog load!")
except Exception:
    print("[ERROR]")
    traceback.print_exc()

# ── Step 6: Inspect what underlyings ARE in _futures_by_underlying ────────
print()
print("=" * 70)
print("STEP 6: All underlyings in _futures_by_underlying (first 30)")
print("=" * 70)

try:
    keys = sorted(resolver._futures_by_underlying.keys())
    print(f"  Total unique underlyings: {len(keys)}")
    for k in keys[:30]:
        entries = resolver._futures_by_underlying[k]
        print(f"    {k:30s} -> {len(entries)} contracts")
    if len(keys) > 30:
        print(f"    ... and {len(keys) - 30} more")
except Exception:
    traceback.print_exc()

# ── Step 7: Try nearest_futures_contract ──────────────────────────────────
print()
print("=" * 70)
print("STEP 7: nearest_futures_contract('NIFTY')")
print("=" * 70)

try:
    nearest = resolver.nearest_futures_contract("NIFTY")
    print(
        f"  Nearest: {nearest.canonical_symbol}  sid={nearest.security_id}  "
        f"expiry={nearest.expiry}  lot={nearest.lot_size}"
    )
except Exception:
    print("[ERROR]")
    traceback.print_exc()

# ── Step 8: Check futures adapter path too ────────────────────────────────
print()
print("=" * 70)
print("STEP 8: broker.futures.get_contracts('NIFTY', None)")
print("=" * 70)

try:
    adapter_contracts = broker.futures.get_contracts("NIFTY", None)
    print(f"  Result: {len(adapter_contracts)} contracts via adapter")
except Exception:
    print("[ERROR]")
    traceback.print_exc()

print()
print("Done.")
