"""Upstox <-> Trade_XV2 domain mapper.

Mirrors Trade_J ``UpstoxDomainMapper``: maps between Upstox REST payloads and
the common ``OrderRequest`` (Pydantic) input model and canonical domain
dataclasses (``Order``/``Quote``/``Position``/etc.), normalises status strings,
and converts wire product / validity / order-type enums to the canonical
Trade_XV2 domain enums.

This module is now a thin facade that delegates to specialised sub-modules:

- :mod:`.equity_mapper` — holdings, positions, trades, fund limits, quotes
- :mod:`.derivatives_mapper` — order placement/modify, historical candles,
  market depth, order responses
- :mod:`.options_mapper` — option contracts and leg field extractors
- :mod:`._base` — shared enum converters and constants

All existing import paths continue to work:

    from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
"""

from __future__ import annotations

from ._base import (
    PROVIDER_ALGO_NAME,
    PROVIDER_IS_AMO,
    PROVIDER_MARKET_PROTECTION,
    instrument_type_from_wire,
    order_type_from_wire,
    order_type_to_wire,
    product_from_wire,
    product_to_wire,
    segment_from_wire,
    segment_to_wire,
    txn_from_wire,
    txn_to_wire,
    validity_from_wire,
    validity_to_wire,
)
from ._base import (
    wire_status_to_domain_status as _wire_status_to_domain_status,
)
from .derivatives_mapper import (
    to_historical_candle,
    to_historical_candles,
    to_market_depth,
    to_modify_payload,
    to_order,
    to_order_response,
    to_place_payload,
)
from .equity_mapper import (
    to_fund_limits,
    to_holding,
    to_position,
    to_quote,
    to_quotes,
    to_trade,
)
from .options_mapper import (
    leg_instrument_key,
    leg_trading_symbol,
    to_option_contract,
)

# Re-export for existing importers of these constants
__all__ = [
    "PROVIDER_ALGO_NAME",
    "PROVIDER_IS_AMO",
    "PROVIDER_MARKET_PROTECTION",
    "UpstoxDomainMapper",
    "_wire_status_to_domain_status",
]


class UpstoxDomainMapper:
    """Static, side-effect-free converters between Upstox wire payloads and
    Trade_XV2 canonical domain dataclasses.

    All methods are ``@staticmethod`` and delegate to implementation
    functions in :mod:`.equity_mapper`, :mod:`.derivatives_mapper`, and
    :mod:`.options_mapper`.
    """

    # -- Status mapping ------------------------------------------------
    normalize_status = staticmethod(_wire_status_to_domain_status)

    # -- Product / validity / order-type / txn / segment / instrument --
    product_to_wire = staticmethod(product_to_wire)
    product_from_wire = staticmethod(product_from_wire)
    validity_to_wire = staticmethod(validity_to_wire)
    validity_from_wire = staticmethod(validity_from_wire)
    order_type_to_wire = staticmethod(order_type_to_wire)
    order_type_from_wire = staticmethod(order_type_from_wire)
    txn_to_wire = staticmethod(txn_to_wire)
    txn_from_wire = staticmethod(txn_from_wire)
    segment_from_wire = staticmethod(segment_from_wire)
    segment_to_wire = staticmethod(segment_to_wire)
    instrument_type_from_wire = staticmethod(instrument_type_from_wire)

    # -- Order payload builders ----------------------------------------
    to_place_payload = staticmethod(to_place_payload)
    to_modify_payload = staticmethod(to_modify_payload)
    to_order_response = staticmethod(to_order_response)

    # -- Quotes --------------------------------------------------------
    to_quote = staticmethod(to_quote)
    to_quotes = staticmethod(to_quotes)

    # -- Holdings / positions / trades / fund limits -------------------
    to_position = staticmethod(to_position)
    to_holding = staticmethod(to_holding)
    to_trade = staticmethod(to_trade)
    to_fund_limits = staticmethod(to_fund_limits)

    # -- Historical data -----------------------------------------------
    to_historical_candle = staticmethod(to_historical_candle)
    to_historical_candles = staticmethod(to_historical_candles)

    # -- Market depth --------------------------------------------------
    to_market_depth = staticmethod(to_market_depth)

    # -- Orders --------------------------------------------------------
    to_order = staticmethod(to_order)

    # -- Option contracts ----------------------------------------------
    to_option_contract = staticmethod(to_option_contract)
    leg_instrument_key = staticmethod(leg_instrument_key)
    leg_trading_symbol = staticmethod(leg_trading_symbol)
