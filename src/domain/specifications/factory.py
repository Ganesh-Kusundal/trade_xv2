"""Specification factory — map an :class:`Instrument` to its Specification.

Pure domain code: depends only on other ``domain`` modules (instruments, value
objects, asset kinds). It never imports ``application`` or ``infrastructure``.

Usage::

    from domain.specifications import get_specification

    spec = get_specification(equity_instrument)
    spec.validate_quantity(qty)
    spec.validate_price(price)
"""

from __future__ import annotations

from typing import Any

from domain.instruments.asset_kind import AssetKind
from domain.specifications.concrete import (
    EquitySpecification,
    FutureSpecification,
    IndexSpecification,
    OptionSpecification,
)
from domain.specifications.specification import Specification


def get_specification(instrument: Any) -> Specification:
    """Return the concrete :class:`Specification` for *instrument*.

    The instrument is inspected via its public surface (``asset_type``,
    ``lot_size``, ``tick_size``) so this works with any ``Instrument`` subtype
    without a hard dependency on the concrete class.
    """
    kind = AssetKind.parse(getattr(instrument, "asset_type", None))
    lot_size = int(getattr(instrument, "lot_size", 1) or 1)
    tick_size = getattr(instrument, "tick_size", None) or _default_tick()

    if kind in (AssetKind.FUTURES, AssetKind.COMMODITY):
        return FutureSpecification(lot_size=lot_size, tick_size=tick_size)
    if kind == AssetKind.OPTIONS:
        return OptionSpecification(lot_size=lot_size, tick_size=tick_size)
    if kind == AssetKind.INDEX:
        return IndexSpecification(tick_size=tick_size)

    # EQUITY / ETF / SPOT / CURRENCY / BOND / CRYPTO / SYNTHETIC → equity rules
    return EquitySpecification(tick_size=tick_size)


def _default_tick() -> Any:
    from domain.constants.market import DEFAULT_TICK_SIZE

    return DEFAULT_TICK_SIZE
