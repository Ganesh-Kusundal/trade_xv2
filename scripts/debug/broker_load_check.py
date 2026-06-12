"""Diagnostic script: why does DhanBroker.from_env() fall back to MockBroker?"""

import sys
import traceback
from pathlib import Path

print("=" * 70)
print("DhanBroker.from_env() diagnostic")
print("=" * 70)

# Step 1: Import
print("\n[1] Importing DhanBroker...")
try:
    from brokers.dhan import DhanBroker

    print("    OK - DhanBroker imported successfully")
except Exception as e:
    print(f"    FAIL - Import error:")
    traceback.print_exc()
    sys.exit(1)

# Step 2: from_env()
env_path = Path(".env.local")
print(f"\n[2] Calling DhanBroker.from_env(env_path={env_path!r})...")
print(f"    .env.local exists: {env_path.exists()}")
print(f"    .env.local absolute: {env_path.resolve()}")

try:
    broker = DhanBroker.from_env(env_path=env_path)
    print(f"    OK - broker type: {type(broker).__name__}")
    print(f"    client_id: {getattr(broker, 'client_id', 'N/A')}")
    print(f"    settings type: {type(getattr(broker, 'settings', None)).__name__}")
except Exception as e:
    print(f"\n    FAIL - from_env() raised {type(e).__name__}:")
    print("-" * 70)
    traceback.print_exc()
    print("-" * 70)
    print("\n>>> This is the exception causing MockBroker fallback! <<<")
    sys.exit(1)

# Step 3: Try live API calls
print("\n[3] Trying live API calls...")

try:
    print("    broker.get_fund_limits()...")
    funds = broker.get_fund_limits()
    print(f"    OK - {funds}")
except Exception as e:
    print(f"    FAIL - {type(e).__name__}:")
    traceback.print_exc()

try:
    print("    broker.get_positions()...")
    positions = broker.get_positions()
    print(f"    OK - {len(positions)} positions: {[p.symbol for p in positions]}")
except Exception as e:
    print(f"    FAIL - {type(e).__name__}:")
    traceback.print_exc()

try:
    print("    broker.get_holdings()...")
    holdings = broker.get_holdings()
    print(f"    OK - {len(holdings)} holdings: {[h.symbol for h in holdings]}")
except Exception as e:
    print(f"    FAIL - {type(e).__name__}:")
    traceback.print_exc()

print("\n" + "=" * 70)
print("Diagnostic complete.")
print("=" * 70)
