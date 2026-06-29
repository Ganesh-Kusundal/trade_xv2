#!/usr/bin/env python3
"""
REALITY CHECK: Broker Connection Verification
This script MUST run without errors to prove the system is working.
No mocks. No fake data. Direct Factory usage.
"""
import os
import sys
from dotenv import load_dotenv

# Ensure workspace is in path
sys.path.insert(0, '/workspace')

load_dotenv('/workspace/.env.local')

def test_dhan_reality():
    print("=== DHAN REALITY CHECK ===")
    
    # 1. Verify Env
    if not os.getenv('DHAN_CLIENT_ID'):
        raise EnvironmentError("❌ CRITICAL: DHAN_CLIENT_ID missing from .env.local")
    print(f"✅ Credentials loaded for Client: {os.getenv('DHAN_CLIENT_ID')}")

    # 2. Import Factory (The ONLY valid way to connect)
    try:
        from brokers.dhan.factory import BrokerFactory as DhanBrokerFactory
        print("✅ Factory imported successfully")
    except ImportError as e:
        raise ImportError(f"❌ CRITICAL: Cannot import Factory: {e}")

    # 3. Instantiate Gateway (Sync operation)
    print("🔄 Initializing Gateway (handling TOTP/RateLimits)...")
    try:
        factory = DhanBrokerFactory()
        # Disable instrument loading for quick connectivity test
        gateway = factory.create(load_instruments=False)
        print("✅ Gateway instance created")
    except Exception as e:
        print(f"❌ CRITICAL: Gateway creation failed: {e}")
        return False

    # 4. Fetch Real Funds (Sync operation - NO AWAIT)
    print("🔄 Fetching REAL funds from Dhan API...")
    try:
        # Call the method, not access as property
        balance = gateway.funds()
        print(f"✅ REAL DATA RECEIVED: Balance = {balance}")
        
        # Verify it's not a mock
        if balance is None:
            raise ValueError("Balance returned None")
            
    except Exception as e:
        print(f"❌ CRITICAL: Failed to fetch real funds: {e}")
        return False

    # 5. Fetch Real Positions
    print("🔄 Fetching REAL positions...")
    try:
        # Call the method, not access as property
        positions = gateway.positions()
        print(f"✅ REAL DATA RECEIVED: {len(positions) if positions else 0} positions found")
    except Exception as e:
        print(f"❌ CRITICAL: Failed to fetch positions: {e}")
        return False

    print("=== DHAN REALITY CHECK PASSED ===\n")
    return True

def test_upstox_reality():
    print("=== UPSTOX REALITY CHECK ===")
    # Similar implementation for Upstox if credentials exist
    if not os.getenv('UPSTOX_API_KEY'):
        print("⚠️ Skipping Upstox (Credentials missing)")
        return True
        
    try:
        from brokers.upstox.factory import UpstoxBrokerFactory
        factory = UpstoxBrokerFactory()
        # Disable instrument loading for quick connectivity test
        gateway = factory.create(load_instruments=False)
        balance = gateway.funds()
        print(f"✅ UPSTOX REAL DATA: {balance}")
        print("=== UPSTOX REALITY CHECK PASSED ===\n")
        return True
    except Exception as e:
        print(f"❌ UPSTOX FAILED: {e}")
        return False

if __name__ == "__main__":
    success = True
    
    try:
        if not test_dhan_reality():
            success = False
    except Exception as e:
        print(f"💥 DHAN TEST CRASHED: {e}")
        success = False

    try:
        if not test_upstox_reality():
            success = False
    except Exception as e:
        print(f"💥 UPSTOX TEST CRASHED: {e}")
        success = False

    if success:
        print("\n🎉 SYSTEM VERIFIED: Real broker connections WORKING.")
        sys.exit(0)
    else:
        print("\n🛑 SYSTEM BROKEN: Real broker connections FAILED.")
        sys.exit(1)
