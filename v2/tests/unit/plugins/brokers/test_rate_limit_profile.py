"""F5 — limiter_from_profile sources cooldown / min-interval from RateLimitProfile."""

from __future__ import annotations

from domain.capabilities.broker_capabilities import RateLimitProfile
from plugins.brokers.common.rate_limit import (
    DHAN_RATE_LIMITS,
    UPSTOX_RATE_LIMITS,
    MultiBucketRateLimiter,
    limiter_from_profile,
    limiter_from_table,
)


def test_limiter_from_profile_returns_multibucket() -> None:
    profile = RateLimitProfile(cooldown_on_429_s=130.0)
    limiter = limiter_from_profile("dhan", profile)
    assert isinstance(limiter, MultiBucketRateLimiter)
    assert set(limiter.categories()) == set(DHAN_RATE_LIMITS.keys())


def test_cooldown_sourced_from_profile_not_60() -> None:
    profile = RateLimitProfile(cooldown_on_429_s=130.0)
    limiter = limiter_from_profile("upstox", profile)
    for name in UPSTOX_RATE_LIMITS:
        bucket = limiter.get_bucket(name)
        assert bucket._cooldown_on_429_s == 130.0
        # restore cooldown also driven by the profile value
        assert bucket._restore_cooldown == 130.0


def test_per_bucket_min_interval_from_profile() -> None:
    profile = RateLimitProfile(
        cooldown_on_429_s=90.0,
        min_interval_ms={"orders": 250, "quotes": 80},
    )
    limiter = limiter_from_profile("dhan", profile)
    assert limiter.get_bucket("orders")._min_interval_s == 0.25
    assert limiter.get_bucket("quotes")._min_interval_s == 0.08
    # buckets without an override keep table values (historical = 200ms)
    assert limiter.get_bucket("historical")._min_interval_s == 0.2


def test_profile_none_falls_back_to_table_constants() -> None:
    limiter = limiter_from_profile("dhan", None)
    ref = limiter_from_table(DHAN_RATE_LIMITS)
    for name in DHAN_RATE_LIMITS:
        assert (
            limiter.get_bucket(name)._cooldown_on_429_s
            == ref.get_bucket(name)._cooldown_on_429_s
        )
        assert (
            limiter.get_bucket(name)._min_interval_s
            == ref.get_bucket(name)._min_interval_s
        )


def test_connections_use_limiter_from_profile() -> None:
    # Read source directly (avoids importing broker packages whose __init__
    # may pull in unrelated modules under concurrent refactoring).
    from pathlib import Path

    import plugins.brokers as pkg

    root = Path(pkg.__path__[0])
    dhan_src = (root / "dhan" / "connection.py").read_text()
    upstox_src = (root / "upstox" / "connection.py").read_text()
    assert "limiter_from_profile" in dhan_src
    assert "limiter_from_profile" in upstox_src
