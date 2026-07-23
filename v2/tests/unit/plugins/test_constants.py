"""Tests for broker constants module."""

from __future__ import annotations

from decimal import Decimal

from plugins.brokers.common.constants import (
    DEFAULT_CURRENCY,
    DEFAULT_FILL_PRICE,
    DEFAULT_TOKEN_TTL_SECONDS,
    DHAN_COOLDOWN_SECONDS,
    PAPER_STARTING_CASH,
    RATE_REDUCTION_FACTOR,
    UPSTOX_COOLDOWN_SECONDS,
    USER_AGENT,
)


def test_default_token_ttl_seconds() -> None:
    assert DEFAULT_TOKEN_TTL_SECONDS == 86400


def test_dhan_cooldown_seconds() -> None:
    assert DHAN_COOLDOWN_SECONDS == 120


def test_upstox_cooldown_seconds() -> None:
    assert UPSTOX_COOLDOWN_SECONDS == 600


def test_default_currency() -> None:
    assert DEFAULT_CURRENCY == "INR"


def test_paper_starting_cash() -> None:
    assert PAPER_STARTING_CASH == Decimal("1000000")


def test_default_fill_price() -> None:
    assert DEFAULT_FILL_PRICE == Decimal("100")


def test_rate_reduction_factor() -> None:
    assert RATE_REDUCTION_FACTOR == 0.5


def test_user_agent() -> None:
    assert USER_AGENT == "TradeXV2/0.1 (+https://github.com/tradex; python-urllib)"
