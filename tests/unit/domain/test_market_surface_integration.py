"""Domain integration: refactored code reads conventions from MarketSurface.

Confirms the domain spots that previously hardcoded ``"NSE"`` / ``0.05`` now
resolve to the default surface — with NO change to their effective values.
"""

from __future__ import annotations

from decimal import Decimal

from domain.constants.market import DEFAULT_EXCHANGE, DEFAULT_TICK_SIZE
from domain.field_mapping import DefaultFieldMapping
from domain.specifications.concrete import EquitySpecification


def test_field_mapping_default_exchange_uses_surface() -> None:
    mapping = DefaultFieldMapping()
    # No exchange key -> falls back to the surface-derived default.
    assert mapping.map_exchange({}) == DEFAULT_EXCHANGE == "NSE"
    # Explicit value still wins.
    assert mapping.map_exchange({"exchange": "BSE"}) == "BSE"


def test_equity_spec_default_tick_uses_surface() -> None:
    spec = EquitySpecification()
    assert spec.tick_size == DEFAULT_TICK_SIZE == Decimal("0.05")
    assert spec.lot_size == 1
    assert spec.instrument_type == "EQUITY"


def test_universe_default_exchange_is_surface() -> None:
    # The default exchange parameter is the surface-derived "NSE".
    import inspect

    from domain.universe import Universe

    sig = inspect.signature(Universe.equity)
    assert sig.parameters["exchange"].default == DEFAULT_EXCHANGE == "NSE"
