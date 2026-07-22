from __future__ import annotations

from domain.capabilities.broker_capabilities import (
    BrokerCapabilities,
    HistoricalRouteConstraint,
    HistoricalWindowConstraint,
    StreamLimitProfile,
)
from domain.capabilities.market_surface import (
    FUTURE_CHAIN,
    LTP,
    OPTION_CHAIN,
    QUOTE,
    RESOLVE,
    MarketCoverage,
)
from domain.constants.exchanges import CDS, MCX, NFO, NSE
from domain.historical.contract_state import ContractState
from domain.instruments.asset_kind import AssetKind
from brokers.common.rate_limit_config import DHAN_RATE_LIMITS, profiles_from_table

_ACTIVE = frozenset({ContractState.ACTIVE, ContractState.AUTO})
_DHAN_HISTORICAL_ROUTES: tuple[HistoricalRouteConstraint, ...] = (
    HistoricalRouteConstraint(AssetKind.EQUITY, NSE, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.INDEX, NSE, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.FUTURES, NFO, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.OPTIONS, NFO, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.FUTURES, MCX, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.OPTIONS, MCX, _ACTIVE),
    HistoricalRouteConstraint(
        AssetKind.OPTIONS,
        NFO,
        frozenset({ContractState.EXPIRED}),
        exact_contract=False,
        rolling_index_options=True,
    ),
)

# Dhan's depth-200 WebSocket API supports exactly one instrument per connection.
# To monitor multiple instruments at 200-level depth, create multiple connections
# (see Depth200ConnectionPool in brokers.providers.dhan.market_data.depth_200).
DHAN_DEPTH_200_MAX_INSTRUMENTS_PER_CONNECTION: int = 1


def dhan_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Dhan broker.

    NOTE ON DEPTH_200 LIMITATION:
        Dhan's depth-200 WebSocket API only supports 1 instrument per connection.
        To monitor multiple instruments at 200-level depth, you must create multiple
        connections. Use Depth200ConnectionPool from brokers.providers.dhan.market_data.depth_200 for
        efficient connection management.
    """
    return BrokerCapabilities(
        broker_id="dhan",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=True,
        supports_depth_200_ws=True,  # LIMITATION: 1 instrument per connection
        supports_option_chain=True,
        supports_polling_fallback=True,
        supports_order_stream=True,
        supports_portfolio_stream=False,
        supports_news=False,
        supports_fundamentals=False,
        supports_super_order=True,
        supports_forever_order=True,
        supports_native_slice_order=True,
        rate_limit_profiles=profiles_from_table(DHAN_RATE_LIMITS),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="5m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="15m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="25m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="60m",
                max_lookback_days=3650,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="1D",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
        ),
        historical_routes=_DHAN_HISTORICAL_ROUTES,
        stream_limits=StreamLimitProfile(
            max_connections=1,
            max_instruments_per_connection=1000,
            max_depth_levels=200,
            supported_stream_modes=frozenset({"LTP", "QUOTE", "FULL", "DEPTH_20", "DEPTH_200"}),
        ),
        latency_class="low",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "MARGIN", "CNC", "MTF"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=1000,
        market_surfaces=frozenset(
            {
                MarketCoverage(AssetKind.EQUITY, NSE, "RELIANCE", frozenset({RESOLVE, QUOTE, LTP})),
                MarketCoverage(AssetKind.INDEX, NSE, "NIFTY", frozenset({RESOLVE, LTP})),
                MarketCoverage(AssetKind.OPTIONS, NFO, "NIFTY", frozenset({OPTION_CHAIN})),
                MarketCoverage(AssetKind.FUTURES, NFO, "NIFTY", frozenset({FUTURE_CHAIN})),
                MarketCoverage(AssetKind.FUTURES, MCX, "GOLD", frozenset({FUTURE_CHAIN, QUOTE})),
                MarketCoverage(AssetKind.OPTIONS, MCX, "GOLD", frozenset({OPTION_CHAIN})),
                MarketCoverage(AssetKind.SPOT, CDS, "USDINR", frozenset({RESOLVE, QUOTE, LTP})),
            }
        ),
    )
