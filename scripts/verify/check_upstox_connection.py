import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from brokers.upstox.auth.config import UpstoxSettingsLoader
from brokers.upstox.auth.token_manager import UpstoxTokenManager
from brokers.upstox.auth.oauth_client import UpstoxOAuthClient

def main():
    print("=" * 60)
    print("UPSTOX CONNECTION & AUTHENTICATION PROBE (NO MOCKS)")
    print("=" * 60)
    
    try:
        # Load settings from environment
        settings = UpstoxSettingsLoader.from_env()
        print(f"✓ Configuration loaded. Auth mode: {settings.auth_mode}")
        
        # Instantiate token manager
        token_manager = UpstoxTokenManager(settings)
        print("✓ Token manager initialized")
        
        # Retrieve bearer token (triggers actual TOTP/interactive flow if needed)
        token = token_manager.bearer_token()
        print("✓ Access token retrieved successfully")
        
        # Instantiate OAuth client
        client = UpstoxOAuthClient(base_url=settings.base_v2)
        
        # Check profile (this is an account/admin endpoint and is expected to fail without static IP)
        print("\n[Optional] Sending live request to private user endpoint /v2/user/profile...")
        expiry = client.fetch_profile(token)
        if expiry > 0:
            print(f"  ✓ User Profile retrieved successfully (IP matches configured Static IP).")
        else:
            print("  ℹ Info: User Profile fetch skipped/failed (expected if current IP is not the registered Static IP).")
            
        # Check market status
        print("\nSending live request to /v2/market/status/NSE...")
        status = client.validate_read_only_token(token)
        if status:
            print("  ✓ NSE Market Status request returned HTTP 200 OK")
        else:
            print("  ✗ NSE Market Status request failed")

        # Check market quote (LTP)
        print("\nSending live request to market data endpoint /v2/market-quote/ltp...")
        try:
            resp = client._session.get(
                f"{settings.base_v2}/v2/market-quote/ltp",
                params={"instrument_key": "NSE_EQ|INE002A01018"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                reliance_data = data.get("NSE_EQ:RELIANCE", {})
                print(f"  ✓ Market Quote (LTP) successful! RELIANCE Last Traded Price: {reliance_data.get('last_price')}")
                quote_success = True
            else:
                print(f"  ✗ Market Quote request failed with status {resp.status_code}: {resp.text}")
                quote_success = False
        except Exception as e:
            print(f"  ✗ Market Quote request failed: {e}")
            quote_success = False

        # Check historical data (Historical Candles)
        print("\nSending live request to historical data endpoint /v2/historical-candle...")
        try:
            # Get daily candles for RELIANCE ending 2026-07-09
            resp = client._session.get(
                f"{settings.base_v2}/v2/historical-candle/NSE_EQ|INE002A01018/day/2026-07-09",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10
            )
            if resp.status_code == 200:
                candles = resp.json().get("data", {}).get("candles", [])
                if candles:
                    print(f"  ✓ Historical Candles successful! Retrieved {len(candles)} days of candles. Latest close: {candles[0][4]}")
                else:
                    print("  ✓ Historical Candles request successful, but empty candle list returned.")
                historical_success = True
            else:
                print(f"  ✗ Historical Candles request failed with status {resp.status_code}: {resp.text}")
                historical_success = False
        except Exception as e:
            print(f"  ✗ Historical Candles request failed: {e}")
            historical_success = False
            
        if status and quote_success and historical_success:
            print("\n✅ SUCCESS: Connection and market/historical data endpoints are working correctly (Static IP not required for data)!")
        else:
            print("\n❌ FAILED: One or more market data connection checks failed.")
            
    except Exception as exc:
        print(f"\n❌ Error during connection validation: {exc}")
        import traceback
        traceback.print_exc()
        
    print("=" * 60)

if __name__ == "__main__":
    main()
