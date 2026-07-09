"""Tick and market-depth validation, mirroring Dhan strict mode.

These helpers centralise the drop rules that previously lived inline in
``brokers/dhan/websocket/market_feed.py`` (see ``_publish_tick``). A quote
or book that fails validation should be *dropped* rather than published,
because malformed packets (e.g. a zero-LTP tick) would otherwise be treated
as real signals by downstream strategies.

Rules (Dhan strict mode, Plan §7.7 / §5.2):

- A quote is dropped when its ``ltp`` is missing (``None``), zero, negative,
  or not a finite number (``NaN`` / ``inf``), or when its ``symbol`` /
  ``instrument`` is missing or empty.
- A depth book is dropped when it is empty or its top-of-book price is
  missing (``None``), zero, or negative.

Numeric comparisons are ``Decimal``-aware and accept ``int`` / ``float`` /
``Decimal`` inputs.
"""

from __future__ import annotations

import logging
import math
from decimal import (
    Decimal,
    InvalidOperation,
)
from typing import Any, Callable, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = ["is_valid_quote", "validate_depth"]


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce ``int`` / ``float`` / ``Decimal`` / ``str`` to ``Decimal``.

    Returns ``None`` for ``None`` or any value that cannot be parsed, or for
    non-finite floats (``NaN`` / ``inf``) which are not representable.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return Decimal(str(value))
    if isinstance(value, (int, str)):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError, TypeError):
            return None
    # Unknown type — refuse to guess.
    return None


def _is_missing_symbol(quote: Mapping[str, Any]) -> bool:
    """True when symbol/instrument is missing or empty."""
    symbol = quote.get("symbol")
    if symbol is None or (isinstance(symbol, str) and symbol.strip() == ""):
        # Fall back to instrument token / id.
        instrument = quote.get("instrument")
        if instrument is None or (isinstance(instrument, str) and instrument.strip() == ""):
            return True
    return False


def is_valid_quote(quote: Mapping[str, Any], log: Optional[Callable[[str], None]] = None) -> bool:
    """Return ``False`` when the quote should be DROPPED (strict mode).

    Args:
        quote: Mapping with at least ``ltp`` and ``symbol`` keys.
        log: Optional callable used to emit a drop reason (e.g. a logger's
            ``warning`` method). When ``None``, the module ``logger`` is used.

    Returns:
        ``True`` if the quote passes validation and may be published,
        ``False`` if it must be dropped.
    """
    if not isinstance(quote, Mapping):
        _emit(log, "tick_dropped_non_mapping_quote")
        return False

    ltp_raw = quote.get("ltp")

    if ltp_raw is None:
        _emit(log, "tick_dropped_missing_ltp")
        return False

    if isinstance(ltp_raw, float) and not math.isfinite(ltp_raw):
        _emit(log, "tick_dropped_non_finite_ltp")
        return False

    ltp = _to_decimal(ltp_raw)
    if ltp is None:
        _emit(log, "tick_dropped_unparsable_ltp")
        return False

    if ltp == 0:
        _emit(log, "tick_dropped_zero_ltp")
        return False

    if ltp < 0:
        _emit(log, "tick_dropped_negative_ltp")
        return False

    if _is_missing_symbol(quote):
        _emit(log, "tick_dropped_missing_symbol")
        return False

    return True


def validate_depth(book: Sequence[Mapping[str, Any]]) -> bool:
    """Return ``False`` when the market-depth ``book`` should be DROPPED.

    A book is dropped when it is empty (or falsy) or its top-of-book price
    is missing (``None``), zero, or negative. The top-of-book price is read
    from the first level's ``price`` key (falling back to ``ltp``).

    Args:
        book: Sequence of price-level mappings (typically bids or asks).

    Returns:
        ``True`` if the book has a valid top-of-book price, ``False`` to drop.
    """
    if not book:
        return False

    top = book[0]
    if not isinstance(top, Mapping):
        return False

    price_raw = top.get("price")
    if price_raw is None:
        price_raw = top.get("ltp")
    if price_raw is None:
        return False

    if isinstance(price_raw, float) and not math.isfinite(price_raw):
        return False

    price = _to_decimal(price_raw)
    if price is None:
        return False

    if price <= 0:
        return False

    return True


def _emit(log: Any, message: str) -> None:
    """Emit a drop reason via ``log`` (default module ``logger.warning``).

    ``log`` may be a logger-like object exposing ``.warning`` or any callable
    accepting a single string argument.
    """
    if log is None:
        logger.warning(message)
        return
    warning = getattr(log, "warning", None)
    if callable(warning):
        warning(message)
    elif callable(log):
        log(message)
