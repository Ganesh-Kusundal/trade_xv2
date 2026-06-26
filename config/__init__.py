"""Central configuration package for TradeXV2.

Provides configuration schema, validation, feature flags, and environment profiles.

Usage::

    from config import (
        load_dhan_config,
        load_upstox_config,
        validate_config,
        FeatureFlags,
        load_profile,
    )

    # Validate configuration at startup
    validate_config()

    # Load broker configs
    dhan_cfg = load_dhan_config()
    upstox_cfg = load_upstox_config()

    # Check feature flags
    if FeatureFlags.SMART_ROUTING:
        # Use smart routing
        pass

    # Load environment profile
    profile = load_profile()
"""

from config.schema import (
    ApiConfig,
    DhanConfig,
    TradingConfig,
    UpstoxConfig,
    load_api_config,
    load_dhan_config,
    load_trading_config,
    load_upstox_config,
)
from config.validator import (
    ConfigValidationError,
    ConfigValidator,
    ValidationProfile,
    validate_config,
)
from config.feature_flags import FeatureFlags, is_enabled, set_flag
from config.profiles import load_profile, EnvironmentProfile

__all__ = [
    # Schema
    "ApiConfig",
    "DhanConfig",
    "TradingConfig",
    "UpstoxConfig",
    "load_api_config",
    "load_dhan_config",
    "load_trading_config",
    "load_upstox_config",
    # Validation
    "ConfigValidationError",
    "ConfigValidator",
    "ValidationProfile",
    "validate_config",
    # Feature Flags
    "FeatureFlags",
    "is_enabled",
    "set_flag",
    # Profiles
    "load_profile",
    "EnvironmentProfile",
]
