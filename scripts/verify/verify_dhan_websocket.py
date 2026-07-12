#!/usr/bin/env python
"""Verify Dhan WebSocket live subscription and market depth streaming."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _connect import bootstrap_or_exit


async def main():
    """Test WebSocket subscriptions and continuous data streaming."""
    print("=" * 70)
    print("DHAN WEBSOCKET STREAMING VERIFICATION")
    print("=" * 70)

    # Create gateway
    try:
        gateway = bootstrap_or_exit("dhan", load_instruments=True)
        print("✅ Created Dhan gateway")
    except Exception as e:
        print(f"❌ Failed to create gateway: {e}")
        return False

    import sys
    test_symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    test_exchange = sys.argv[2] if len(sys.argv) > 2 else "NSE"
    tick_count = 0
    depth_updates = 0
    start_time = None

    # Test 1: Subscribe to live market data (LTP updates)
    print(f"\n📡 Subscribing to {test_symbol} live market data...")
    try:
        def on_tick(tick):
            nonlocal tick_count, start_time
            if start_time is None:
                start_time = time.time()
            tick_count += 1
            elapsed = time.time() - start_time
            print(f"   Tick #{tick_count} @ {elapsed:.1f}s: {tick}")
            if tick_count >= 5:  # Stop after 5 ticks
                return False

        # Subscribe to stream
        handle = gateway.stream(test_symbol, test_exchange, mode="LTP", on_tick=on_tick)
        print(f"✅ Subscribed to {test_symbol} LTP stream")

        # Wait for ticks
        print(f"   Listening for 10 seconds or 5 ticks (whichever comes first)...")
        wait_start = time.time()
        while tick_count < 5 and (time.time() - wait_start) < 10:
            await asyncio.sleep(0.1)

        if tick_count > 0:
            print(f"\n✅ Received {tick_count} live LTP ticks in {time.time() - start_time:.1f}s")
        else:
            print(f"⚠️  No ticks received (WebSocket may not be connected)")

        # Try to stop the stream
        try:
            if hasattr(handle, "stop"):
                handle.stop()
            print(f"✅ Stream stopped")
        except Exception as e:
            print(f"⚠️  Error stopping stream: {e}")

    except Exception as e:
        print(f"❌ LTP subscription failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Subscribe to market depth (order book updates)
    print(f"\n📡 Subscribing to {test_symbol} market depth (D5)...")
    start_time = None
    try:
        # Check support first to give a clean skip message
        nse_allowed = ("NSE", "NSE_EQ", "NFO", "NSE_FNO", "IDX_I")
        if test_exchange not in nse_allowed:
            print(f"ℹ️ Skipping depth stream test (Dhan only supports WebSocket depth streaming for NSE segments, got: {test_exchange})")
            depth_handle = None
        else:
            def on_depth(depth):
                nonlocal depth_updates, start_time
                if start_time is None:
                    start_time = time.time()
                depth_updates += 1
                elapsed = time.time() - start_time
                if depth.bids and depth.asks:
                    best_bid = depth.bids[0]
                    best_ask = depth.asks[0]
                    spread = float(best_ask.price - best_bid.price)
                    print(f"   Depth #{depth_updates} @ {elapsed:.1f}s: Bid {best_bid.price}x{best_bid.quantity} | Ask {best_ask.price}x{best_ask.quantity} | Spread: ₹{spread:.2f}")
                if depth_updates >= 5:  # Stop after 5 updates
                    return False

            # Subscribe to depth stream
            depth_handle = gateway.stream_depth(
                test_symbol, test_exchange, depth_type="DEPTH_5", on_depth=on_depth
            )
            print(f"✅ Subscribed to {test_symbol} depth stream")

            # Wait for depth updates
            print(f"   Listening for 10 seconds or 5 updates (whichever comes first)...")
            wait_start = time.time()
            while depth_updates < 5 and (time.time() - wait_start) < 10:
                await asyncio.sleep(0.1)

            if depth_updates > 0:
                print(f"\n✅ Received {depth_updates} depth updates in {time.time() - start_time:.1f}s")
            else:
                print(f"⚠️  No depth updates received (WebSocket may not be connected)")

            # Try to stop the stream
            try:
                if hasattr(depth_handle, "stop"):
                    depth_handle.stop()
                print(f"✅ Depth stream stopped")
            except Exception as e:
                print(f"⚠️  Error stopping depth stream: {e}")

    except Exception as e:
        print(f"❌ Depth subscription failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Summary
    print("\n" + "=" * 70)
    if tick_count > 0 or depth_updates > 0:
        print("✅ WEBSOCKET STREAMING IS WORKING")
        print(f"   - Received {tick_count} LTP ticks")
        print(f"   - Received {depth_updates} depth updates")
        print("=" * 70)
        return True
    else:
        print("⚠️  NO CONTINUOUS DATA RECEIVED")
        print("   WebSocket may not be properly connected to Dhan's live feed")
        print("   Check: network connectivity, DHAN_ACCESS_TOKEN validity, Dhan API status")
        print("=" * 70)
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
