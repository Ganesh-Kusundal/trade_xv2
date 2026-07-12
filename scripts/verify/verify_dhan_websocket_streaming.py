#!/usr/bin/env python
"""Verify Dhan WebSocket live subscription and continuous market depth data streaming.

Tests:
1. Live market data subscription (LTP updates)
2. Market depth subscription (D5 continuous updates)
3. Data continuity and latency
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

# Add repo to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root / "scripts"))
from _connect import bootstrap_or_exit


class WebSocketStreamingTest:
    """Test WebSocket subscriptions and continuous data."""

    def __init__(self):
        self.test_symbol = "RELIANCE"
        self.test_exchange = "NSE"
        self.gateway = None
        self.ltp_ticks = []
        self.depth_updates = []

    async def setup(self):
        """Create gateway and load instruments."""
        print("\n" + "=" * 80)
        print("DHAN WEBSOCKET STREAMING VERIFICATION")
        print("=" * 80)

        try:
            print("\n📦 Creating Dhan gateway and loading instruments...")
            self.gateway = bootstrap_or_exit("dhan", load_instruments=True)
            print("✅ Gateway created and instruments loaded")
            return True
        except Exception as e:
            print(f"❌ Failed to create gateway: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def test_ltp_subscription(self):
        """Test LTP (last traded price) live subscription."""
        print(f"\n📡 TEST 1: LTP Live Subscription")
        print(f"   Symbol: {self.test_symbol}, Exchange: {self.test_exchange}")
        print(f"   Listening for 15 seconds...")

        tick_count = 0
        start_time = time.time()
        subscription_handle = None

        def on_ltp_tick(tick):
            nonlocal tick_count
            tick_count += 1
            elapsed = time.time() - start_time
            self.ltp_ticks.append({
                "timestamp": datetime.now(),
                "data": tick,
                "elapsed": elapsed
            })
            print(f"   ✓ Tick #{tick_count:3d} @ {elapsed:6.1f}s: {tick}")

        try:
            subscription_handle = self.gateway.stream(
                self.test_symbol,
                self.test_exchange,
                mode="LTP",
                on_tick=on_ltp_tick
            )
            print(f"✅ Subscribed to LTP stream")

            # Wait for ticks
            wait_start = time.time()
            while (time.time() - wait_start) < 15:
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"❌ LTP subscription error: {e}")
            return False
        finally:
            if subscription_handle and hasattr(subscription_handle, "stop"):
                try:
                    subscription_handle.stop()
                    print(f"✅ LTP stream unsubscribed")
                except Exception as e:
                    print(f"⚠️  Error unsubscribing: {e}")

        # Report results
        elapsed_total = time.time() - start_time
        if tick_count > 0:
            freq = tick_count / elapsed_total
            print(f"\n✅ LTP Subscription Working:")
            print(f"   - Received {tick_count} ticks in {elapsed_total:.1f}s")
            print(f"   - Frequency: {freq:.1f} ticks/sec")
            return True
        else:
            print(f"\n⚠️  No LTP ticks received (WebSocket may not be connected)")
            return False

    async def test_depth_subscription(self):
        """Test market depth (order book) live subscription."""
        print(f"\n📡 TEST 2: Market Depth (D5) Live Subscription")
        print(f"   Symbol: {self.test_symbol}, Exchange: {self.test_exchange}")
        print(f"   Listening for 15 seconds...")

        depth_count = 0
        start_time = time.time()
        subscription_handle = None

        def on_depth_update(depth):
            nonlocal depth_count
            depth_count += 1
            elapsed = time.time() - start_time

            if depth.bids and depth.asks and depth.bids[0].price and depth.asks[0].price:
                best_bid = depth.bids[0]
                best_ask = depth.asks[0]
                spread = float(best_ask.price - best_bid.price)
                spread_pct = (spread / float(best_bid.price)) * 100

                self.depth_updates.append({
                    "timestamp": datetime.now(),
                    "bid_price": float(best_bid.price),
                    "bid_qty": best_bid.quantity,
                    "ask_price": float(best_ask.price),
                    "ask_qty": best_ask.quantity,
                    "spread": spread,
                    "spread_pct": spread_pct,
                    "total_bids": len(depth.bids),
                    "total_asks": len(depth.asks),
                    "elapsed": elapsed
                })

                print(f"   ✓ Depth #{depth_count:3d} @ {elapsed:6.1f}s: "
                      f"Bid {best_bid.price}x{best_bid.quantity:4d} | "
                      f"Ask {best_ask.price}x{best_ask.quantity:4d} | "
                      f"Spread: ₹{spread:7.2f} ({spread_pct:5.3f}%)")

        try:
            subscription_handle = self.gateway.stream_depth(
                self.test_symbol,
                self.test_exchange,
                depth_type="DEPTH_5",
                on_depth=on_depth_update
            )
            print(f"✅ Subscribed to depth stream")

            # Wait for updates
            wait_start = time.time()
            while (time.time() - wait_start) < 15:
                await asyncio.sleep(0.5)

        except Exception as e:
            print(f"❌ Depth subscription error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if subscription_handle and hasattr(subscription_handle, "stop"):
                try:
                    subscription_handle.stop()
                    print(f"✅ Depth stream unsubscribed")
                except Exception as e:
                    print(f"⚠️  Error unsubscribing: {e}")

        # Report results
        elapsed_total = time.time() - start_time
        if depth_count > 0:
            freq = depth_count / elapsed_total
            avg_spread = sum(u["spread"] for u in self.depth_updates) / len(self.depth_updates)
            avg_spread_pct = sum(u["spread_pct"] for u in self.depth_updates) / len(self.depth_updates)

            print(f"\n✅ Depth Subscription Working:")
            print(f"   - Received {depth_count} updates in {elapsed_total:.1f}s")
            print(f"   - Frequency: {freq:.1f} updates/sec")
            print(f"   - Avg spread: ₹{avg_spread:.2f} ({avg_spread_pct:.3f}%)")
            print(f"   - Min spread: ₹{min(u['spread'] for u in self.depth_updates):.2f}")
            print(f"   - Max spread: ₹{max(u['spread'] for u in self.depth_updates):.2f}")
            return True
        else:
            print(f"\n❌ No depth updates received")
            return False

    async def test_data_continuity(self):
        """Test data continuity and latency."""
        if not self.depth_updates:
            print(f"\n⚠️  No depth data to analyze")
            return True

        print(f"\n📊 TEST 3: Data Continuity & Latency Analysis")

        # Calculate update intervals
        intervals = []
        for i in range(1, len(self.depth_updates)):
            interval = self.depth_updates[i]["elapsed"] - self.depth_updates[i-1]["elapsed"]
            intervals.append(interval)

        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)

            print(f"✅ Data Continuity Check:")
            print(f"   - Total updates: {len(self.depth_updates)}")
            print(f"   - Avg interval: {avg_interval*1000:.1f}ms")
            print(f"   - Min interval: {min_interval*1000:.1f}ms")
            print(f"   - Max interval: {max_interval*1000:.1f}ms")

            # Check for gaps
            gaps = [i for i in intervals if i > 1.0]  # More than 1 second gap
            if gaps:
                print(f"   ⚠️  Found {len(gaps)} gaps > 1 second")
            else:
                print(f"   ✅ No significant gaps in data flow")

        return True

    async def run_all_tests(self):
        """Run all streaming tests."""
        if not await self.setup():
            return False

        results = []

        # Test 1: LTP subscription
        try:
            result1 = await self.test_ltp_subscription()
            results.append(("LTP Subscription", result1))
        except Exception as e:
            print(f"❌ LTP test failed: {e}")
            results.append(("LTP Subscription", False))

        # Small delay between tests
        await asyncio.sleep(2)

        # Test 2: Depth subscription
        try:
            result2 = await self.test_depth_subscription()
            results.append(("Depth Subscription", result2))
        except Exception as e:
            print(f"❌ Depth test failed: {e}")
            results.append(("Depth Subscription", False))

        # Test 3: Data continuity
        try:
            result3 = await self.test_data_continuity()
            results.append(("Data Continuity", result3))
        except Exception as e:
            print(f"❌ Continuity test failed: {e}")
            results.append(("Data Continuity", False))

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} - {test_name}")

        overall_success = self.depth_updates and len(self.depth_updates) > 0
        if overall_success:
            print("\n✅ WEBSOCKET STREAMING IS WORKING")
            print("   Live subscriptions and continuous data delivery confirmed")
        else:
            print("\n⚠️  WebSocket streaming may not be fully operational")
            print("   Check network connectivity and Dhan API status")

        print("=" * 80)
        return overall_success


async def main():
    """Main entry point."""
    try:
        tester = WebSocketStreamingTest()
        success = await tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
