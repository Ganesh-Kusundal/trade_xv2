"""Provider rate-limit configuration tables.

Shared algorithm: :class:`infrastructure.resilience.rate_limiter.MultiBucketRateLimiter`.
Only these tables differ per provider — do not fork the limiter.

Maps to :class:`domain.capabilities.broker_capabilities.RateLimitProfile`
via :func:`profiles_from_table`.
"""

from __future__ import annotations

from typing import Any

from domain.capabilities.broker_capabilities import RateLimitProfile

# Logical buckets consumed by create_rate_limiter / MultiBucketRateLimiter.
# Values are (sustained_rps, burst_rps, min_interval_ms, cooldown_on_429_s).

DHAN_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {
        "sustained_rps": 25.0,
        "burst_rps": 50.0,
        "min_interval_ms": 40,
        "cooldown_on_429_s": 130,
    },
    "quotes": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
    },
    "historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 130,
    },
    "admin": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 130,
    },
}

UPSTOX_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {
        "sustained_rps": 10.0,
        "burst_rps": 20.0,
        "min_interval_ms": 100,
        "cooldown_on_429_s": 60,
    },
    "quotes": {
        "sustained_rps": 25.0,
        "burst_rps": 50.0,
        "min_interval_ms": 40,
        "cooldown_on_429_s": 60,
    },
    "historical": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "option_chain": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "funds": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "positions": {
        "sustained_rps": 5.0,
        "burst_rps": 10.0,
        "min_interval_ms": 200,
        "cooldown_on_429_s": 60,
    },
    "holdings": {
        "sustained_rps": 2.0,
        "burst_rps": 5.0,
        "min_interval_ms": 500,
        "cooldown_on_429_s": 60,
    },
}

PAPER_RATE_LIMITS: dict[str, dict[str, float]] = {
    "orders": {
        "sustained_rps": 1000.0,
        "burst_rps": 1000.0,
        "min_interval_ms": 0,
        "cooldown_on_429_s": 0,
    },
    "quotes": {
        "sustained_rps": 1000.0,
        "burst_rps": 1000.0,
        "min_interval_ms": 0,
        "cooldown_on_429_s": 0,
    },
    "historical": {
        "sustained_rps": 1000.0,
        "burst_rps": 1000.0,
        "min_interval_ms": 0,
        "cooldown_on_429_s": 0,
    },
}


def profiles_from_table(table: dict[str, dict[str, float]]) -> tuple[RateLimitProfile, ...]:
    """Build RateLimitProfile tuple from a provider rate-limit table."""
    profiles: list[RateLimitProfile] = []
    for endpoint_class, cfg in table.items():
        profiles.append(
            RateLimitProfile(
                endpoint_class=endpoint_class,
                sustained_rps=float(cfg["sustained_rps"]),
                burst_rps=float(cfg["burst_rps"]),
                min_interval_ms=int(cfg["min_interval_ms"]),
                cooldown_on_429_s=float(cfg["cooldown_on_429_s"]),
            )
        )
    return tuple(profiles)


def rate_limit_table_for(broker_id: str) -> dict[str, dict[str, float]]:
    """Resolve the config table for a broker id."""
    key = (broker_id or "paper").lower().strip()
    if key == "dhan":
        return DHAN_RATE_LIMITS
    if key == "upstox":
        return UPSTOX_RATE_LIMITS
    return PAPER_RATE_LIMITS


def build_limiter(broker_id: str) -> Any:
    """Create MultiBucketRateLimiter from the shared table for ``broker_id``."""
    from infrastructure.resilience.rate_limiter import create_rate_limiter

    from domain.capabilities.broker_capabilities import BrokerCapabilities

    table = rate_limit_table_for(broker_id)
    caps = BrokerCapabilities(
        broker_id=broker_id,
        rate_limit_profiles=profiles_from_table(table),
    )
    return create_rate_limiter(broker_id, caps=caps)


__all__ = [
    "DHAN_RATE_LIMITS",
    "UPSTOX_RATE_LIMITS",
    "PAPER_RATE_LIMITS",
    "profiles_from_table",
    "rate_limit_table_for",
    "build_limiter",
]
