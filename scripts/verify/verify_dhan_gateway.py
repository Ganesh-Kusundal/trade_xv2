#!/usr/bin/env python
"""Verify Dhan gateway connections and market data endpoints."""

import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

# Add repo to path
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))
from _connect import bootstrap_or_exit
from brokers.dhan.config.settings import DhanSettingsLoader


def main():
    """Test Dhan gateway connections and data endpoints."""
    print("=" * 70)
    print("DHAN GATEWAY VERIFICATION")
    print("=" * 70)

    # Load environment
    env_path = Path(".env.local")
    if not env_path.exists():
        print("❌ .env.local not found. Create it with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN")
        return False

    # Load settings
    try:
        settings = DhanSettingsLoader.from_env()
        print(f"\n✅ Loaded settings from environment")
        print(f"   Client ID: {settings.client_id}")
        print(f"   Environment: {settings.environment}")
    except Exception as e:
        print(f"❌ Failed to load settings: {e}")
        return False

    # Create gateway
    try:
        print(f"\n   Creating Dhan gateway (loading instruments, this may take a moment)...")
        gateway = bootstrap_or_exit("dhan", env_path=env_path, load_instruments=True)
        print(f"✅ Created Dhan gateway and loaded instruments")
    except Exception as e:
        print(f"❌ Failed to create gateway: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 1: Check capabilities
    try:
        caps = gateway.capabilities()
        print(f"\n✅ Gateway capabilities retrieved")
        print(f"   Capabilities: {caps}")
    except Exception as e:
        print(f"❌ Failed to get capabilities: {e}")
        # Don't fail on this, continue with data endpoint tests
        print(f"   Continuing with data endpoint tests...")
        pass

    # Test 2: LTP endpoint
    test_symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    test_exchange = sys.argv[2] if len(sys.argv) > 2 else "NSE"
    try:
        ltp = gateway.ltp(test_symbol, test_exchange)
        if isinstance(ltp, Decimal) and ltp > 0:
            print(f"\n✅ LTP endpoint working")
            print(f"   {test_symbol} ({test_exchange}): ₹{ltp}")
        else:
            print(f"❌ LTP returned invalid type: {type(ltp)}")
            return False
    except Exception as e:
        print(f"❌ LTP endpoint failed: {e}")
        return False

    # Test 3: Quote endpoint
    try:
        quote = gateway.quote(test_symbol, test_exchange)
        print(f"\n✅ Quote endpoint working")
        print(f"   Symbol: {quote.symbol}")
        print(f"   LTP: ₹{quote.ltp}")
        print(f"   Open: ₹{quote.open}")
        print(f"   High: ₹{quote.high}")
        print(f"   Low: ₹{quote.low}")
        print(f"   Close: ₹{quote.close}")
        print(f"   Volume: {quote.volume}")
    except Exception as e:
        print(f"❌ Quote endpoint failed: {e}")
        return False

    # Test 4: Depth endpoint
    try:
        depth = gateway.depth(test_symbol, test_exchange)
        if depth.bids and depth.asks:
            print(f"\n✅ Depth endpoint working")
            print(f"   Bid (best): {depth.bids[0].price} x {depth.bids[0].quantity}")
            print(f"   Ask (best): {depth.asks[0].price} x {depth.asks[0].quantity}")
            print(f"   Total bids: {len(depth.bids)}")
            print(f"   Total asks: {len(depth.asks)}")
        else:
            print(f"⚠️  Depth returned but with empty bids/asks")
    except Exception as e:
        print(f"❌ Depth endpoint failed: {e}")
        return False

    # Test 5: History endpoint
    try:
        df = gateway.history(test_symbol, test_exchange, timeframe="1D", lookback_days=5)
        if isinstance(df, pd.DataFrame) and len(df) > 0:
            print(f"\n✅ History endpoint working")
            print(f"   Retrieved {len(df)} candles")
            print(f"   Columns: {', '.join(df.columns.tolist())}")
            print(f"   Date range: {df.index[0]} to {df.index[-1]}" if df.index.name else f"   First row: {df.iloc[0].to_dict()}")
        else:
            print(f"❌ History returned invalid data: {type(df)}, len={len(df) if hasattr(df, '__len__') else 'N/A'}")
            return False
    except Exception as e:
        print(f"❌ History endpoint failed: {e}")
        return False

    # Test 6: Batch LTP endpoint
    if test_exchange == "MCX":
        test_symbols = ["CRUDEOIL-20Jul2026-FUT", "NATURALGAS-28Jul2026-FUT", "SILVER-03Jul2026-FUT"]
    else:
        test_symbols = ["RELIANCE", "TCS", "INFY"]
    try:
        batch_result = gateway.ltp_batch(test_symbols, test_exchange)
        if isinstance(batch_result, dict) and len(batch_result) > 0:
            print(f"\n✅ LTP batch endpoint working")
            for sym in test_symbols:
                if sym in batch_result:
                    print(f"   {sym}: ₹{batch_result[sym]}")
        else:
            print(f"❌ Batch LTP returned invalid type: {type(batch_result)}")
            return False
    except Exception as e:
        print(f"❌ LTP batch endpoint failed: {e}")
        return False

    # Test 7: History batch endpoint
    try:
        batch_df = gateway.history_batch(test_symbols[:2], test_exchange, timeframe="1D", lookback_days=3)
        if isinstance(batch_df, pd.DataFrame) and len(batch_df) > 0:
            print(f"\n✅ History batch endpoint working")
            print(f"   Retrieved {len(batch_df)} total rows across {batch_df['symbol'].nunique()} symbols")
            for sym in batch_df["symbol"].unique():
                count = len(batch_df[batch_df["symbol"] == sym])
                print(f"   {sym}: {count} rows")
        else:
            print(f"❌ Batch history returned invalid data: {type(batch_df)}")
            return False
    except Exception as e:
        print(f"❌ History batch endpoint failed: {e}")
        return False

    # Summary
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED - Dhan gateway is working correctly")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
