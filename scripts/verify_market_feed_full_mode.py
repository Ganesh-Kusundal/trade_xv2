#!/usr/bin/env python
"""Verify Dhan market feed in FULL mode (LTP + OHLC + volume + best bid/ask)."""

import asyncio
import sys
import time
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from brokers.dhan.factory import BrokerFactory


async def main():
    print("=" * 80)
    print("DHAN MARKET FEED — FULL MODE VERIFICATION")
    print("=" * 80)

    factory = BrokerFactory()
    print("\n📦 Creating gateway and loading instruments...")
    gateway = factory.create(load_instruments=True)
    print("✅ Gateway ready")

    test_cases = [
        ("RELIANCE", "NSE"),
        ("CRUDEOIL", "MCX"),
    ]

    for symbol, exchange in test_cases:
        print(f"\n📡 Subscribing to {symbol} ({exchange}) in FULL mode...")
        tick_count = 0
        start_time = time.time()
        handle = None

        def on_tick(tick, _symbol=symbol):
            nonlocal tick_count
            tick_count += 1
            elapsed = time.time() - start_time
            print(f"   ✓ Tick #{tick_count} @ {elapsed:5.1f}s: {tick}")

        try:
            handle = gateway.stream(symbol, exchange, mode="FULL", on_tick=on_tick)
            print(f"✅ Subscribed ({symbol}/{exchange}, FULL mode)")

            wait_start = time.time()
            while (time.time() - wait_start) < 12:
                await asyncio.sleep(0.5)

            if tick_count > 0:
                print(f"✅ Received {tick_count} FULL-mode ticks for {symbol} in {time.time()-start_time:.1f}s")
            else:
                print(f"⚠️  No ticks received for {symbol} ({exchange})")

        except Exception as e:
            print(f"❌ FULL mode subscription failed for {symbol}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if handle and hasattr(handle, "stop"):
                try:
                    handle.stop()
                    print(f"✅ Unsubscribed {symbol}")
                except Exception as e:
                    print(f"⚠️  Error unsubscribing: {e}")

        await asyncio.sleep(2)

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
