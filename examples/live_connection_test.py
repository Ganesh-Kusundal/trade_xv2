#!/usr/bin/env python3
"""Live broker connectivity test - tests actual data flow."""

from __future__ import annotations

import tradex
from datetime import date


def test_paper_connection():
    """Test paper broker (always works)."""
    print("=" * 50)
    print("Testing PAPER broker connection...")
    print("=" * 50)
    
    try:
        session = tradex.connect("paper")
        print(f"✅ Connected: {session.describe()}")
        
        stock = session.universe.equity("RELIANCE")
        quote = stock.refresh()
        print(f"✅ RELIANCE LTP: {stock.ltp}")
        
        history = stock.history(timeframe="1D", days=5)
        print(f"✅ History bars: {history.bar_count}")
        
        session.close()
        return True
    except Exception as exc:
        print(f"❌ Paper connection failed: {exc}")
        return False


def test_dhan_connection():
    """Test Dhan broker (live credentials required)."""
    print("\n" + "=" * 50)
    print("Testing DHAN broker connection...")
    print("=" * 50)
    
    try:
        session = tradex.connect("dhan", mode="market")
        print(f"✅ Connected: {session.describe()}")
        
        stock = session.universe.equity("RELIANCE")
        quote = stock.refresh()
        print(f"✅ RELIANCE LTP: {stock.ltp}")
        
        # Depth if available
        if stock.broker and stock.broker.has("depth20"):
            depth = stock.broker.depth20()
            print(f"✅ Depth best bid: {depth.best_bid.price if depth.best_bid else 'None'}")
            print(f"✅ Depth levels: {len(depth.bids)} bid, {len(depth.asks)} ask")
        
        # Index option chain
        idx = session.universe.index("NIFTY")
        chain = idx.option_chain(expiry="2026-07-31")
        print(f"✅ NIFTY ATM: {chain.atm.strike if chain.atm else 'None'}")
        print(f"✅ Chain strikes: {len(chain.strikes)}")
        
        session.close()
        return True
    except Exception as exc:
        print(f"❌ Dhan connection failed: {type(exc).__name__}: {exc}")
        return False


def test_upstox_connection():
    """Test Upstox broker (live credentials required)."""
    print("\n" + "=" * 50)
    print("Testing UPSTOX broker connection...")
    print("=" * 50)
    
    try:
        session = tradex.connect("upstox", mode="market")
        print(f"✅ Connected: {session.describe()}")
        
        stock = session.universe.equity("RELIANCE")
        quote = stock.refresh()
        print(f"✅ RELIANCE LTP: {stock.ltp}")
        
        session.close()
        return True
    except Exception as exc:
        print(f"❌ Upstox connection failed: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    paper_ok = test_paper_connection()
    dhan_ok = test_dhan_connection()
    upstox_ok = test_upstox_connection()
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Paper broker:  {'✅ OK' if paper_ok else '❌ FAILED'}")
    print(f"Dhan broker:   {'✅ OK' if dhan_ok else '❌ FAILED (may require valid tokens)'}")
    print(f"Upstox broker: {'✅ OK' if upstox_ok else '❌ FAILED (may require valid tokens)'}")