#!/usr/bin/env python3
"""
Quick broker connection test using the standard factory pattern.

Usage:
    python scripts/test_broker_connection.py
    python scripts/test_broker_connection.py --broker upstox
"""

import argparse
import sys
from pathlib import Path

def test_dhan():
    """Test Dhan broker connection using factory pattern."""
    print("=" * 60)
    print("DHAN BROKER CONNECTION TEST")
    print("=" * 60)

    try:
        from brokers.dhan.factory import BrokerFactory

        # Create gateway via factory (STANDARD FLOW)
        factory = BrokerFactory()
        gateway = factory.create(
            env_path=Path('.env.local'),
            load_instruments=False  # Skip for speed
        )

        print("✅ Gateway created via factory")

        # Check connection status via describe
        status = gateway.describe()
        print(f"✅ Connection status: {status.get('broker', 'Unknown')} - OK")

        # Test funds API
        funds = gateway.funds()
        print(f"✅ Funds: ₹{funds.available_balance} available")

        # Test positions API
        positions = gateway.positions()
        print(f"✅ Positions: {len(positions) if positions else 0} open positions")

        # Test orders API
        orders = gateway.get_orderbook()
        print(f"✅ Orders: {len(orders) if orders else 0} pending orders")

        print("\n🎉 DHAN CONNECTION SUCCESSFUL")
        return True

    except Exception as e:
        print(f"\n❌ DHAN CONNECTION FAILED: {e}")
        return False


def test_upstox():
    """Test Upstox broker connection using factory pattern."""
    print("=" * 60)
    print("UPSTOX BROKER CONNECTION TEST")
    print("=" * 60)

    try:
        from brokers.upstox.factory import UpstoxBrokerFactory

        # Create gateway via factory (STANDARD FLOW)
        factory = UpstoxBrokerFactory()
        gateway = factory.create(
            env_path=Path('.env.local'),
            load_instruments=False  # Skip for speed
        )

        print("✅ Gateway created via factory")

        # Check connection status via describe (if available) or funds
        try:
            status = gateway.describe()
            print(f"✅ Connection status: {status.get('broker', 'Unknown')} - OK")
        except AttributeError:
            print("✅ Gateway connected (describe not available)")

        # Test funds API
        funds = gateway.funds()
        print(f"✅ Funds: ₹{funds.available_balance} available")

        # Test positions API
        positions = gateway.positions()
        print(f"✅ Positions: {len(positions) if positions else 0} open positions")

        # Test orders API
        orders = gateway.get_orderbook()
        print(f"✅ Orders: {len(orders) if orders else 0} pending orders")

        print("\n🎉 UPSTOX CONNECTION SUCCESSFUL")
        return True

    except Exception as e:
        print(f"\n❌ UPSTOX CONNECTION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test broker connections")
    parser.add_argument("--broker", choices=["dhan", "upstox", "both"], default="both",
                       help="Which broker to test (default: both)")
    args = parser.parse_args()

    results = {}

    if args.broker in ["dhan", "both"]:
        results["dhan"] = test_dhan()

    if args.broker in ["upstox", "both"]:
        results["upstox"] = test_upstox()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for broker, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{broker.upper()}: {status}")

    sys.exit(0 if all(results.values()) else 1)
