"""Feature flag infrastructure for experimental features.

Provides a lightweight, type-safe toggle system for controlling
experimental features without heavy framework dependencies.

All flags default to False (opt-in) for safety. Flags can be
controlled via environment variables or toggled at runtime.

Usage::

    from config.feature_flags import FeatureFlags

    # Type-safe access (loads from env on first access)
    if FeatureFlags.is_enabled("SMART_ROUTING"):
        # Use smart routing logic
        pass

    # Runtime toggle (for admin endpoints)
    FeatureFlags.set_flag("SMART_ROUTING", True)

    # Check if flag is enabled
    if FeatureFlags.is_enabled("INTELLIGENT_GATEWAY"):
        # Use intelligent gateway
        pass
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Feature flag system for experimental features.

    Flags are loaded from environment variables on first access.
    Environment variable format: FEATURE_<FLAG_NAME>=true/false

    All flags default to False for safety (opt-in model).
    """

    # Flag definitions with descriptions
    FLAG_DEFINITIONS: dict[str, dict[str, Any]] = {
        "SMART_ROUTING": {
            "env_var": "FEATURE_SMART_ROUTING",
            "default": False,
            "description": "Enable intelligent broker routing for automatic broker selection",
        },
        "INTELLIGENT_GATEWAY": {
            "env_var": "FEATURE_INTELLIGENT_GATEWAY",
            "default": False,
            "description": "Enable intelligent gateway for advanced order routing",
        },
        "ADVANCED_ORDER_TYPES": {
            "env_var": "FEATURE_ADVANCED_ORDER_TYPES",
            "default": False,
            "description": "Enable advanced order types (bracket, cover, etc.)",
        },
        "EXPERIMENTAL_STRATEGIES": {
            "env_var": "FEATURE_EXPERIMENTAL_STRATEGIES",
            "default": False,
            "description": "Enable experimental trading strategies",
        },
    }

    # Runtime flag state (lazy-loaded from env)
    _flags: dict[str, bool] | None = None
    _initialized: bool = False

    # Class attributes for property-style access
    SMART_ROUTING: bool = False
    INTELLIGENT_GATEWAY: bool = False
    ADVANCED_ORDER_TYPES: bool = False
    EXPERIMENTAL_STRATEGIES: bool = False

    @classmethod
    def _initialize(cls) -> None:
        """Load flags from environment variables."""
        if cls._initialized:
            return

        cls._flags = {}
        for flag_name, definition in cls.FLAG_DEFINITIONS.items():
            env_var = definition["env_var"]
            default = definition["default"]
            value = os.environ.get(env_var, "")

            if value:
                # Parse boolean from string
                enabled = value.lower() in ("1", "true", "yes", "on")
                cls._flags[flag_name] = enabled
                # Update class attribute for property access
                setattr(cls, flag_name, enabled)
                logger.info("Feature flag %s = %s (from %s)", flag_name, enabled, env_var)
            else:
                cls._flags[flag_name] = default
                logger.debug("Feature flag %s = %s (default)", flag_name, default)

        cls._initialized = True

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Ensure flags are loaded from environment."""
        if not cls._initialized:
            cls._initialize()

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check if a feature flag is enabled.

        Args:
            flag_name: Flag name (e.g., "SMART_ROUTING").

        Returns:
            True if flag is enabled, False otherwise.
        """
        cls._ensure_initialized()
        return cls._flags.get(flag_name, False)  # type: ignore[return-value]

    @classmethod
    def set_flag(cls, flag_name: str, value: bool) -> None:
        """Set a feature flag at runtime.

        This allows runtime toggling of features (e.g., from admin endpoints).

        Args:
            flag_name: Flag name (e.g., "SMART_ROUTING").
            value: True to enable, False to disable.

        Raises:
            ValueError: If flag_name is not a known flag.
        """
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        old_value = cls._flags.get(flag_name, False)  # type: ignore[assignment]
        cls._flags[flag_name] = value  # type: ignore[index]
        
        # Update class attributes for property access
        if flag_name in ("SMART_ROUTING", "INTELLIGENT_GATEWAY", "ADVANCED_ORDER_TYPES", "EXPERIMENTAL_STRATEGIES"):
            setattr(cls, flag_name, value)

        if old_value != value:
            logger.info(
                "Feature flag %s changed: %s -> %s",
                flag_name,
                old_value,
                value,
            )

    @classmethod
    def get_all_flags(cls) -> dict[str, bool]:
        """Get all feature flags and their current state.

        Returns:
            Dict mapping flag names to their boolean values.
        """
        cls._ensure_initialized()
        return dict(cls._flags)  # type: ignore[arg-type]

    @classmethod
    def get_flag_info(cls, flag_name: str) -> dict[str, Any] | None:
        """Get detailed information about a feature flag.

        Args:
            flag_name: Flag name.

        Returns:
            Dict with flag metadata or None if flag not found.
        """
        if flag_name not in cls.FLAG_DEFINITIONS:
            return None

        cls._ensure_initialized()
        definition = cls.FLAG_DEFINITIONS[flag_name]
        current_value = cls._flags.get(flag_name, False)  # type: ignore[assignment]

        return {
            "name": flag_name,
            "enabled": current_value,
            "env_var": definition["env_var"],
            "description": definition["description"],
            "default": definition["default"],
        }

    @classmethod
    def reset(cls) -> None:
        """Reset all flags to default state (reloads from env).

        Useful for testing or configuration reload scenarios.
        """
        cls._flags = None
        cls._initialized = False
        # Reset class attributes
        cls.SMART_ROUTING = False
        cls.INTELLIGENT_GATEWAY = False
        cls.ADVANCED_ORDER_TYPES = False
        cls.EXPERIMENTAL_STRATEGIES = False
        cls._initialize()


# Module-level convenience functions
def is_enabled(flag_name: str) -> bool:
    """Check if a feature flag is enabled.

    Args:
        flag_name: Flag name (e.g., "SMART_ROUTING").

    Returns:
        True if flag is enabled.
    """
    return FeatureFlags.is_enabled(flag_name)


def set_flag(flag_name: str, value: bool) -> None:
    """Set a feature flag at runtime.

    Args:
        flag_name: Flag name.
        value: True to enable, False to disable.
    """
    FeatureFlags.set_flag(flag_name, value)
