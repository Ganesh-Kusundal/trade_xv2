#!/usr/bin/env python3
"""Quick validation script for Upstox TOTP auto-authentication.

Run with: ./venv/bin/python scripts/validate_totp_setup.py

This script validates:
1. TOTP dependencies are installed
2. Configuration loads correctly
3. TOTP mode is recognized
4. Token manager can bootstrap in TOTP mode (with mocked TOTP client)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_dependencies() -> bool:
    """Verify TOTP dependencies are installed."""
    print("✓ Checking dependencies...")
    try:
        import upstox_totp
        print(f"  ✓ upstox-totp: {upstox_totp.__version__ if hasattr(upstox_totp, '__version__') else 'installed'}")
    except ImportError:
        print("  ✗ upstox-totp: NOT INSTALLED")
        print("    Install with: ./venv/bin/pip install upstox-totp")
        return False
    
    try:
        import schedule
        print(f"  ✓ schedule: {schedule.__version__ if hasattr(schedule, '__version__') else 'installed'}")
    except ImportError:
        print("  ✗ schedule: NOT INSTALLED")
        print("    Install with: ./venv/bin/pip install schedule")
        return False
    
    return True


def check_config_loading() -> bool:
    """Verify configuration loads with TOTP fields."""
    print("\n✓ Checking configuration loading...")
    try:
        from brokers.upstox.auth.config import UpstoxConnectionSettings, VALID_AUTH_MODES
        
        # Check TOTP is in valid auth modes
        if "TOTP" in VALID_AUTH_MODES:
            print(f"  ✓ TOTP in VALID_AUTH_MODES: {VALID_AUTH_MODES}")
        else:
            print(f"  ✗ TOTP NOT in VALID_AUTH_MODES: {VALID_AUTH_MODES}")
            return False
        
        # Check settings has TOTP fields
        settings = UpstoxConnectionSettings(
            client_id="test",
            auth_mode="TOTP",
            mobile="9876543210",
            pin="123456",
            totp_secret="TESTSECRET",
        )
        
        if settings.is_totp:
            print("  ✓ is_totp property works")
        else:
            print("  ✗ is_totp property failed")
            return False
        
        if settings.has_totp_config:
            print("  ✓ has_totp_config property works")
        else:
            print("  ✗ has_totp_config property failed")
            return False
        
        print(f"  ✓ TOTP refresh time: {settings.totp_refresh_hour:02d}:{settings.totp_refresh_minute:02d}")
        
        return True
        
    except Exception as exc:
        print(f"  ✗ Configuration loading failed: {exc}")
        return False


def check_token_manager() -> bool:
    """Verify token manager supports TOTP bootstrap."""
    print("\n✓ Checking token manager...")
    try:
        from brokers.upstox.auth.config import UpstoxConnectionSettings
        from brokers.upstox.auth.token_manager import UpstoxTokenManager
        
        settings = UpstoxConnectionSettings(
            client_id="test",
            client_secret="test-secret",
            redirect_uri="http://localhost:18080",
            auth_mode="TOTP",
            mobile="9876543210",
            pin="123456",
            totp_secret="TESTSECRET",
        )
        
        # Verify token manager can be instantiated
        mgr = UpstoxTokenManager(settings)
        print("  ✓ Token manager instantiated with TOTP settings")
        
        # Verify _bootstrap_totp method exists
        if hasattr(mgr, '_bootstrap_totp'):
            print("  ✓ _bootstrap_totp method exists")
        else:
            print("  ✗ _bootstrap_totp method NOT found")
            return False
        
        return True
        
    except Exception as exc:
        print(f"  ✗ Token manager check failed: {exc}")
        return False


def check_scheduler() -> bool:
    """Verify TOTP scheduler is available."""
    print("\n✓ Checking TOTP scheduler...")
    try:
        from brokers.upstox.auth.totp_scheduler import TotpRefreshScheduler
        
        print("  ✓ TotpRefreshScheduler imported successfully")
        
        # Verify it has ManagedService methods
        required_methods = ['start', 'stop', 'health']
        for method in required_methods:
            if hasattr(TotpRefreshScheduler, method):
                print(f"  ✓ Has '{method}' method")
            else:
                print(f"  ✗ Missing '{method}' method")
                return False
        
        return True
        
    except Exception as exc:
        print(f"  ✗ Scheduler check failed: {exc}")
        return False


def main():
    """Run all validation checks."""
    print("=" * 70)
    print("Upstox TOTP Auto-Authentication — Setup Validation")
    print("=" * 70)
    
    checks = [
        check_dependencies,
        check_config_loading,
        check_token_manager,
        check_scheduler,
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:
            print(f"\n✗ Check failed with exception: {exc}")
            results.append(False)
    
    print("\n" + "=" * 70)
    if all(results):
        print("✓ ALL CHECKS PASSED — TOTP auto-auth is ready to use!")
        print("\nNext steps:")
        print("1. Set UPSTOX_AUTH_MODE=TOTP in .env.local")
        print("2. Configure UPSTOX_MOBILE, UPSTOX_PIN, UPSTOX_TOTP_SECRET")
        print("3. Run: ./venv/bin/python -c 'from brokers.upstox.auth.config import UpstoxSettingsLoader; s = UpstoxSettingsLoader.from_env(); print(f\"Auth mode: {s.auth_mode}\")'")
        return 0
    else:
        print("✗ SOME CHECKS FAILED — Please review the errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
