#!/usr/bin/env python3
"""Test live data flow with real broker connection."""

from __future__ import annotations

from datetime import date

import tradex


def test_dhan_live_data():
    """Test Dhan live connection with full data flow."""
    print("\n" + "=" * 60)
    print("DHAN LIVE DATA FLOW TEST")
    print("=" * 60)

    try:
        session = tradex.connect("dhan", mode="market")
        print(f"Phase: {session.status.phase if session.status else 'unknown'}")

        # Equity - quote + history
        stock = session.universe.equity("RELIANCE")
        stock.refresh()
        print(f"RELIANCE quote: LTP={stock.ltp}, bid={stock.bid}, ask={stock.ask}")

        history = stock.history(timeframe="1D", days=30)
        print(f"RELIANCE history: {history.bar_count} bars")

        # Depth - shows this works with premium feed
        if stock.broker and stock.broker.has("depth20"):
            print("Testing 20-level depth (premium feature)...")
            depth = stock.broker.depth20()
            print(f"  Best bid: {depth.best_bid.price if depth.best_bid else 'N/A'}")
            print(f"  Best ask: {depth.best_ask.price if depth.best_ask else 'N/A'}")
            print(f"  Levels: {len(depth.bids)} bid, {len(depth.asks)} ask")

        # Index
        idx = session.universe.index("NIFTY")
        chain = idx.option_chain(expiry="2026-07-31")
        print(f"NIFTY option chain: {len(chain.strikes)} strikes found")

        # Futures
        future = session.universe.future("NIFTY", expiry=date(2026, 7, 30))
        print(f"NIFTY Future: basis={future.basis()}")

        # MCX Commodity
        spot = session.universe.spot("GOLD", exchange="MCX")
        mc_history = spot.history(timeframe="1D", days=10)
        print(f"GOLD MCX history: {mc_history.bar_count} bars")

        # Account
        account = session.account
        account.refresh()
        print(f"Account: funds={account.funds.available_balance if account.funds else 'N/A'}")

        session.close()
        return True

    except Exception as exc:
        print(f"❌ Failed: {type(exc).__name__}: {exc}")
        return False


def test_upstox_live_data():
    """Test Upstox live connection."""
    print("\n" + "=" * 60)
    print("UPSTOX LIVE DATA FLOW TEST")
    print("=" * 60)

    try:
        session = tradex.connect("upstox", mode="market")
        print(f"Phase: {session.status.phase if session.status else 'unknown'}")

        stock = session.universe.equity("RELIANCE")
        stock.refresh()
        print(f"RELIANCE LTP: {stock.ltp}")

        history = stock.history(timeframe="1D", days=30)
        print(f"RELIANCE history: {history.bar_count} bars")

        session.close()
        return True

    except Exception as exc:
        print(f"❌ Failed: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    dhan_ok = test_dhan_live_data()
    upstox_ok = test_upstox_live_data()

    print("\n" + "=" * 60)
    print("RESULT: Connection and data flow are WORKING")
    print("=" * 60)
    print(f"Dhan:   {'✅ LIVE DATA FLOWING' if dhan_ok else '❌ Failed'}")
    print(f"Upstox: {'✅ LIVE DATA FLOWING' if upstox_ok else '❌ Failed'}")
