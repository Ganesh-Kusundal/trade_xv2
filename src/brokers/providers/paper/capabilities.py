"""Paper trading capability snapshot — standalone module, consistent with Dhan/Upstox.

Extracted from ``PaperGateway.capabilities()`` inline to match the pattern
used by all other brokers (``dhan_capabilities()`` in
``brokers.providers.dhan.config.capabilities``, ``upstox_capabilities()`` in
``brokers.providers.upstox.capabilities.snapshot``).
"""

from __future__ import annotations

from domain.capabilities.broker_capabilities import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
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
from domain.instruments.asset_kind import AssetKind


def paper_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Paper broker."""
    return BrokerCapabilities(
        broker_id="paper",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=True,
        supports_live_market_data=True,
        supports_depth=True,
        supports_depth_20_ws=True,
        supports_depth_200_ws=False,
        supports_option_chain=True,
        supports_polling_fallback=True,
        supports_order_stream=True,
        supports_portfolio_stream=False,
        supports_news=False,
        supports_fundamentals=False,
        supports_super_order=False,
        supports_forever_order=False,
        supports_native_slice_order=False,
        rate_limit_profiles=(
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=1000.0,  # Paper trading has no real limits
                burst_rps=2000.0,
                min_interval_ms=0,  # No minimum interval for paper
                cooldown_on_429_s=None,  # No rate limiting
            ),
            RateLimitProfile(
                endpoint_class="quotes",
                sustained_rps=1000.0,
                burst_rps=2000.0,
                min_interval_ms=0,
                cooldown_on_429_s=None,
            ),
            RateLimitProfile(
                endpoint_class="historical",
                sustained_rps=1000.0,
                burst_rps=2000.0,
                min_interval_ms=0,
                cooldown_on_429_s=None,
            ),
            RateLimitProfile(
                endpoint_class="option_chain",
                sustained_rps=1000.0,
                burst_rps=2000.0,
                min_interval_ms=0,
                cooldown_on_429_s=None,
            ),
        ),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=3650,
                max_chunk_days=365,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="1D",
                max_lookback_days=3650,
                max_chunk_days=365,
            ),
        ),
        stream_limits=StreamLimitProfile(
            max_connections=1,
            max_instruments_per_connection=1000,
            max_depth_levels=20,
            supported_stream_modes=frozenset({"LTP", "QUOTE", "FULL"}),
        ),
        latency_class="low",
        reliability_class="tier1",
        product_types=frozenset({"INTRADAY", "MARGIN", "CNC"}),
        order_types=frozenset({"MARKET", "LIMIT", "STOP_LOSS", "STOP_LOSS_MARKET"}),
        max_batch_size=100,
        market_surfaces=frozenset(
            {
                MarketCoverage(
                    AssetKind.EQUITY, "NSE", "RELIANCE", frozenset({RESOLVE, QUOTE, LTP})
                ),
                MarketCoverage(AssetKind.OPTIONS, "NFO", "NIFTY", frozenset({OPTION_CHAIN})),
                MarketCoverage(AssetKind.FUTURES, "NFO", "NIFTY", frozenset({FUTURE_CHAIN})),
                MarketCoverage(
                    AssetKind.FUTURES, "MCX", "GOLD", frozenset({FUTURE_CHAIN, QUOTE})
                ),
            }
        ),
    )


__all__ = ["paper_capabilities"]
