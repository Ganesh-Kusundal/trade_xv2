#!/usr/bin/env python3
"""Quick Dhan gateway connection check — run from project root.

Usage:
    python scripts/check_dhan_connection.py
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.chdir(ROOT)


def main():
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    print("=" * 60)
    print("  DHAN GATEWAY CONNECTION CHECK")
    print("=" * 60)

    # ── 1. Load settings ──────────────────────────────────────────
    print("\n[1/6] Loading settings from .env.local ...")
    try:
        from brokers.dhan.config.settings import DhanSettingsLoader

        settings = DhanSettingsLoader.from_env(env_path=env_path)
        print(f"  client_id     : {settings.client_id[:4]}****")
        print(f"  has_token     : {settings.has_access_token}")
        print(f"  has_totp      : {settings.has_totp}")
        print(f"  base_url      : {settings.base_url}")
        print(f"  allow_orders  : {settings.allow_live_orders}")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # ── 2. Create gateway via factory ─────────────────────────────
    print("\n[2/6] Creating Dhan gateway (bootstrap) ...")
    t0 = time.monotonic()
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from _connect import bootstrap_or_exit

        gateway = bootstrap_or_exit("dhan", env_path=env_path, load_instruments=True)
        elapsed = time.monotonic() - t0
        print(f"  Gateway created in {elapsed:.1f}s")
    except Exception as e:
        print(f"  FAIL: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # ── 3. Check describe ─────────────────────────────────────────
    print("\n[3/6] Broker describe ...")
    try:
        desc = gateway.describe()
        for k, v in desc.items():
            print(f"  {k:20s}: {v}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 4. Check capabilities ─────────────────────────────────────
    print("\n[4/6] Broker capabilities ...")
    try:
        caps = gateway.capabilities()
        print(f"  {caps}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 5. Fetch funds ────────────────────────────────────────────
    print("\n[5/6] Fetching funds (GET /fundlimit) ...")
    try:
        balance = gateway.funds()
        print(f"  available_balance : {balance.available_balance}")
        print(f"  sod_limit         : {balance.sod_limit}")
        print(f"  collateral        : {balance.collateral_amount}")
        print(f"  utilized          : {balance.utilized_amount}")
        print(f"  withdrawable      : {balance.withdrawable_balance}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── 6. Fetch LTP (quick market data test) ────────────────────
    print("\n[6/6] Fetching LTP for RELIANCE (quick data test) ...")
    try:
        from decimal import Decimal

        ltp = gateway.ltp("RELIANCE", exchange="NSE")
        print(f"  RELIANCE LTP = ₹{ltp}")
    except Exception as e:
        print(f"  FAIL: {e}")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  CONNECTION CHECK COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
