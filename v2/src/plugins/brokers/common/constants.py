"""Shared constants for broker plugins."""

from __future__ import annotations

from decimal import Decimal

DEFAULT_TOKEN_TTL_SECONDS = 86400
DHAN_COOLDOWN_SECONDS = 120
UPSTOX_COOLDOWN_SECONDS = 600
DEFAULT_CURRENCY = "INR"
PAPER_STARTING_CASH = Decimal("1000000")
DEFAULT_FILL_PRICE = Decimal("100")
RATE_REDUCTION_FACTOR = 0.5
USER_AGENT = "TradeXV2/0.1 (+https://github.com/tradex; python-urllib)"
