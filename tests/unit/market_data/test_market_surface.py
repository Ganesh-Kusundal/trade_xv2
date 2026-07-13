"""Tests for the MarketSurface abstraction and its config profiles.

These prove:
* paisa->rupee->paisa round-trips are lossless,
* the default surface equals the historical hardcoded constants,
* the config profile registry exposes the default surface.
"""

from __future__ import annotations

from decimal import Decimal

from config.profiles.market_surface import (
    MARKET_SURFACES,
    get_market_surface,
    register_market_surface,
)
from domain.conventions import (
    DEFAULT_MARKET_SURFACE,
    PAISA_SCALE,
    MarketSurface,
    get_default_market_surface,
)


def test_default_surface_matches_legacy_constants() -> None:
    """Default surface must equal the old hardcoded NSE/INR/paisa values."""
    s = DEFAULT_MARKET_SURFACE
    assert s.exchange == "NSE"
    assert s.currency == "INR"
    assert s.price_tick == Decimal("0.05")
    assert s.lot_size == 1
    assert s.risk_free_rate == 0.065
    assert s.price_scale == PAISA_SCALE == 100


def test_domain_constants_equal_legacy_surface() -> None:
    """domain.constants.market now *reads* from the default surface."""
    from domain.constants.market import (
        DEFAULT_CURRENCY,
        DEFAULT_EXCHANGE,
        DEFAULT_PRICE_SCALE,
        DEFAULT_RISK_FREE_RATE,
        DEFAULT_TICK_SIZE,
    )

    s = get_default_market_surface()
    assert DEFAULT_TICK_SIZE == s.price_tick == Decimal("0.05")
    assert DEFAULT_EXCHANGE == s.exchange == "NSE"
    assert DEFAULT_CURRENCY == s.currency == "INR"
    assert DEFAULT_PRICE_SCALE == s.price_scale == 100
    assert DEFAULT_RISK_FREE_RATE == s.risk_free_rate == 0.065


def test_paisa_rupee_round_trip() -> None:
    """paisa -> rupee -> paisa must be lossless."""
    s = DEFAULT_MARKET_SURFACE
    for rupee in (Decimal("0.00"), Decimal("123.45"), Decimal("9999.99")):
        paisa = s.to_paisa(rupee)
        assert isinstance(paisa, int)
        assert s.to_rupee(paisa) == rupee


def test_to_paisa_to_rupee_convention() -> None:
    assert DEFAULT_MARKET_SURFACE.to_paisa(Decimal("123.45")) == 12345
    assert DEFAULT_MARKET_SURFACE.to_rupee(12345) == Decimal("123.45")


def test_tick_helpers() -> None:
    s = DEFAULT_MARKET_SURFACE
    assert s.snap_to_tick(Decimal("100.13")) == Decimal("100.15")
    assert s.snap_to_tick(Decimal("100.12")) == Decimal("100.10")
    assert s.is_tick_aligned(Decimal("100.05"))
    assert not s.is_tick_aligned(Decimal("100.07"))


def test_config_profile_default_is_surface() -> None:
    assert get_market_surface() is DEFAULT_MARKET_SURFACE
    assert get_market_surface("NSE_INR") is DEFAULT_MARKET_SURFACE
    assert "NSE_INR" in MARKET_SURFACES


def test_register_custom_surface() -> None:
    custom = MarketSurface(
        exchange="NSE",
        currency="INR",
        price_tick=Decimal("0.01"),
        lot_size=75,
        risk_free_rate=0.06,
        price_scale=100,
    )
    register_market_surface("NSE_FUT", custom)
    try:
        assert get_market_surface("NSE_FUT") is custom
        # custom surface still round-trips
        assert custom.to_rupee(custom.to_paisa(Decimal("12.34"))) == Decimal("12.34")
    finally:
        MARKET_SURFACES.pop("NSE_FUT", None)
