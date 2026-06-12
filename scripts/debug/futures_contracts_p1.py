#!/usr/bin/env python3
"""Phase 1: Reproduce the bug (no catalog load)."""

import sys
import traceback
from pathlib import Path

print("=" * 70)
print("STEP 1: Creating DhanBroker from .env.local")
print("=" * 70)

try:
    from brokers.dhan import DhanBroker

    broker = DhanBroker.from_env(env_path=Path(".env.local"))
    print(f"[OK] DhanBroker created - client_id={broker.client_id}")
except Exception:
    print("[FAIL] Could not create DhanBroker:")
    traceback.print_exc()
    sys.exit(1)

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
        print("  >>> BUG REPRODUCED: empty list - CLI shows 'No contracts found'")
except Exception:
    print("[ERROR]")
    traceback.print_exc()

print()
print("Done (phase 1).")
