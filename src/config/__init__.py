"""Central configuration package for TradeXV2.

Provides configuration schema, validation, and environment profiles.

Usage::

    from config import (
        validate_config,
        load_profile,
    )

    # Validate configuration at startup
    validate_config()

    # Load environment profile
    profile = load_profile()
"""

from config.defaults import DEFAULT_CONFIG, get_config, reset_config
from config.profiles import EnvironmentProfile, load_profile
from config.schema import (
    ApiConfig,
    AppConfig,
    TradingConfig,
    load_api_config,
    load_trading_config,
)
from config.validator import (
    ConfigValidationError,
    ConfigValidator,
    ValidationProfile,
    validate_config,
)

__all__ = [
    "DEFAULT_CONFIG",
    # Schema
    "ApiConfig",
    # Central AppConfig
    "AppConfig",
    # Validation
    "ConfigValidationError",
    "ConfigValidator",
    "EnvironmentProfile",
    "TradingConfig",
    "ValidationProfile",
    "get_config",
    "load_api_config",
    # Profiles
    "load_profile",
    "load_trading_config",
    "reset_config",
    "validate_config",
]
