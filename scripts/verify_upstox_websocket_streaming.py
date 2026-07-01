#!/usr/bin/env python
"""Verify Upstox WebSocket live subscription and continuous market data streaming."""

import asyncio
import sys
import time
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from brokers.upstox.factory import UpstoxBrokerFactory


async def main():
    print("=" * 80)
    print("UPSTOX WEBSOCKET STREAMING VERIFICATION")
    print("=" * 80)

    try:
        factory = UpstoxBrokerFactory()
        print("\n📦 Creating Upstox gateway and loading instruments...")
        gateway = factory.create(load_instruments=True)
        print("✅ Gateway created")
    except Exception as e:
        print(f"❌ Failed to create gateway: {e}")
        import traceback
        traceback.print_exc()
        return False

    test_symbol = "RELIANCE"
    test_exchange = "NSE"

    # Test 1: LTP stream
    print(f"\n📡 TEST 1: LTP Live Subscription ({test_symbol}/{test_exchange})")
    tick_count = 0
    start_time = time.time()
    handle = None

    def on_tick(tick):
        nonlocal tick_count
        tick_count += 1
        elapsed = time.time() - start_time
        print(f"   ✓ Tick #{tick_count} @ {elapsed:5.1f}s: {tick}")

    try:
        handle = gateway.stream(test_symbol, test_exchange, mode="LTP", on_tick=on_tick)
        print("✅ Subscribed to LTP stream")

        wait_start = time.time()
        while (time.time() - wait_start) < 15:
            await asyncio.sleep(0.5)

        if tick_count > 0:
            print(f"✅ Received {tick_count} LTP ticks in {time.time()-start_time:.1f}s")
        else:
            print("⚠️  No LTP ticks received")

    except Exception as e:
        print(f"❌ LTP subscription failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if handle and hasattr(handle, "stop"):
            try:
                handle.stop()
                print("✅ LTP stream unsubscribed")
            except Exception as e:
                print(f"⚠️  Error unsubscribing: {e}")

    await asyncio.sleep(2)

    # Test 2: Depth stream
    print(f"\n📡 TEST 2: Market Depth (D5) Live Subscription ({test_symbol}/{test_exchange})")
    depth_count = 0
    start_time = time.time()
    depth_handle = None

    def on_depth(depth):
        nonlocal depth_count
        depth_count += 1
        elapsed = time.time() - start_time
        if depth.bids and depth.asks and depth.bids[0].price and depth.asks[0].price:
            best_bid = depth.bids[0]
            best_ask = depth.asks[0]
            spread = float(best_ask.price - best_bid.price)
            print(f"   ✓ Depth #{depth_count} @ {elapsed:5.1f}s: "
                  f"Bid {best_bid.price}x{best_bid.quantity} | "
                  f"Ask {best_ask.price}x{best_ask.quantity} | Spread: ₹{spread:.2f}")

    try:
        depth_handle = gateway.stream_depth(
            test_symbol, test_exchange, depth_type="DEPTH_5", on_depth=on_depth
        )
        print("✅ Subscribed to depth stream")

        wait_start = time.time()
        while (time.time() - wait_start) < 15:
            await asyncio.sleep(0.5)

        if depth_count > 0:
            print(f"✅ Received {depth_count} depth updates in {time.time()-start_time:.1f}s")
        else:
            print("⚠️  No depth updates received")

    except Exception as e:
        print(f"❌ Depth subscription failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if depth_handle and hasattr(depth_handle, "stop"):
            try:
                depth_handle.stop()
                print("✅ Depth stream unsubscribed")
            except Exception as e:
                print(f"⚠️  Error unsubscribing: {e}")

    print("\n" + "=" * 80)
    overall = tick_count > 0 or depth_count > 0
    if overall:
        print("✅ UPSTOX WEBSOCKET STREAMING IS WORKING")
    else:
        print("⚠️  No live data received on either stream")
    print(f"   LTP ticks: {tick_count} | Depth updates: {depth_count}")
    print("=" * 80)
    return overall


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
