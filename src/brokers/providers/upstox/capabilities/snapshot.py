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
from brokers.common.rate_limit_config import UPSTOX_RATE_LIMITS, profiles_from_table

_ACTIVE = frozenset({ContractState.ACTIVE, ContractState.AUTO})
_EXPIRED = frozenset({ContractState.EXPIRED, ContractState.AUTO})
_UPSTOX_HISTORICAL_ROUTES: tuple[HistoricalRouteConstraint, ...] = (
    HistoricalRouteConstraint(AssetKind.EQUITY, NSE, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.INDEX, NSE, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.FUTURES, NFO, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.OPTIONS, NFO, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.FUTURES, MCX, _ACTIVE),
    HistoricalRouteConstraint(AssetKind.OPTIONS, MCX, _ACTIVE),
    HistoricalRouteConstraint(
        AssetKind.OPTIONS, NFO, _EXPIRED, requires_entitlement="upstox_plus"
    ),
    HistoricalRouteConstraint(
        AssetKind.FUTURES, NFO, _EXPIRED, requires_entitlement="upstox_plus"
    ),
    HistoricalRouteConstraint(
        AssetKind.OPTIONS, MCX, _EXPIRED, requires_entitlement="upstox_plus"
    ),
    HistoricalRouteConstraint(
        AssetKind.FUTURES, MCX, _EXPIRED, requires_entitlement="upstox_plus"
    ),
)


def upstox_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Upstox broker."""
    return BrokerCapabilities(
        broker_id="upstox",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,  # Plus plan client: expired_options.py
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=False,
        supports_depth_200_ws=False,
        supports_option_chain=True,
        supports_polling_fallback=False,
        supports_order_stream=True,
        supports_portfolio_stream=True,
        supports_news=True,
        supports_fundamentals=True,
        supports_super_order=False,
        supports_forever_order=True,
        supports_native_slice_order=True,  # slice_adapter / place-order slice flag
        rate_limit_profiles=profiles_from_table(UPSTOX_RATE_LIMITS),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="3m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="5m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="15m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="30m",
                max_lookback_days=30,
                max_chunk_days=30,
            ),
            HistoricalWindowConstraint(
                timeframe="60m",
                max_lookback_days=90,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="4H",
                max_lookback_days=90,
                max_chunk_days=90,
            ),
            HistoricalWindowConstraint(
                timeframe="1D",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
            HistoricalWindowConstraint(
                timeframe="1W",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
            HistoricalWindowConstraint(
                timeframe="1M",
                max_lookback_days=3650,
                max_chunk_days=730,
            ),
        ),
        historical_routes=_UPSTOX_HISTORICAL_ROUTES,
        stream_limits=StreamLimitProfile(
            max_connections=2,
            max_instruments_per_connection=5000,
            max_depth_levels=None,
            supported_stream_modes=frozenset({"ltpc", "option_greeks", "full", "full_d30"}),
            combined_mode_caps={
                "ltpc": 2000,
                "option_greeks": 2000,
                "full": 1500,
                "full_d30": 1500,
            },
        ),
        latency_class="medium",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "MARGIN", "CNC"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=500,  # REST market-quote multi-key limit (docs UDAPI100042/43)
        market_surfaces=frozenset(
            {
                MarketCoverage(AssetKind.EQUITY, NSE, "RELIANCE", frozenset({RESOLVE, QUOTE, LTP})),
                MarketCoverage(AssetKind.INDEX, NSE, "NIFTY", frozenset({RESOLVE, LTP})),
                MarketCoverage(AssetKind.OPTIONS, NFO, "NIFTY", frozenset({OPTION_CHAIN})),
                MarketCoverage(AssetKind.FUTURES, NFO, "NIFTY", frozenset({FUTURE_CHAIN})),
                MarketCoverage(AssetKind.FUTURES, MCX, "GOLD", frozenset({FUTURE_CHAIN, QUOTE})),
                MarketCoverage(AssetKind.SPOT, CDS, "USDINR", frozenset({RESOLVE, QUOTE, LTP})),
            }
        ),
    )
