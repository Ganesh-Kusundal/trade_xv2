"""Environment-specific configuration profiles.

Loads profile based on APP_ENV environment variable:
- dev: Relaxed validation, verbose logging, mock brokers allowed
- staging: Strict validation, real brokers, debug endpoints enabled
- prod: Maximum strictness, real brokers, no debug endpoints

Usage::

    from config.profiles import load_profile

    profile = load_profile()  # Loads from APP_ENV or defaults to dev
"""

from __future__ import annotations

import os

from config.profiles.base import (
    BaseProfile,
    DevProfile,
    EnvironmentProfile,
    ProdProfile,
    StagingProfile,
)

__all__ = [
    "BaseProfile",
    "DevProfile",
    "EnvironmentProfile",
    "ProdProfile",
    "StagingProfile",
    "load_profile",
]

_PROFILES = {
    "dev": DevProfile,
    "staging": StagingProfile,
    "prod": ProdProfile,
}


def load_profile(profile_name: str | None = None) -> EnvironmentProfile:
    """Load environment profile."""
    if profile_name is None:
        profile_name = os.environ.get("APP_ENV", "dev")

    profile_class = _PROFILES.get(profile_name)
    if profile_class is None:
        raise ValueError(
            f"Unknown profile '{profile_name}'. Available profiles: {list(_PROFILES.keys())}"
        )

    return profile_class()
