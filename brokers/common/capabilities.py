"""Full broker capability model — runtime feature/limit matrix.

``BrokerCapabilities`` is the single source of truth for what a broker can do.
Routing, UI gating, and feature access decisions query this object at runtime
rather than branching on broker names.

The old ``BrokerCapabilities`` in ``brokers.common.gateway`` is retained for
backward compatibility.  New code uses this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Sub-profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitProfile:
    """Rate limit envelope for one endpoint class.

    endpoint_class    — e.g. ``"orders"``, ``"quotes"``, ``"historical"``,
                        ``"option_chain"``.
    sustained_rps     — maximum sustained request rate (requests per second).
    burst_rps         — peak burst rate; None if same as sustained.
    min_interval_ms   — minimum time between consecutive requests (ms); None if
                        no per-request floor.
    cooldown_on_429_s — mandatory back-off after a 429 response (seconds); None
                        if broker does not enforce a cooldown window.
    """

    endpoint_class: str
    sustained_rps: float
    burst_rps: float | None = None
    min_interval_ms: int | None = None
    cooldown_on_429_s: int | None = None


@dataclass(frozen=True)
class HistoricalWindowConstraint:
    """Constraints on how far back historical data can be fetched.

    timeframe                  — candle interval this constraint applies to,
                                 e.g. ``"1m"``, ``"5m"``, ``"1D"``.
    max_lookback_days          — maximum calendar days from today that can be
                                 requested in a single or federated query.
    max_chunk_days             — maximum days per individual API request chunk.
    supports_expired_instruments — whether expired options/futures contracts are
                                  accessible through this broker for this timeframe.
    """

    timeframe: str
    max_lookback_days: int
    max_chunk_days: int
    supports_expired_instruments: bool = False


@dataclass(frozen=True)
class StreamLimitProfile:
    """Per-broker streaming limits.

    max_connections              — maximum concurrent WebSocket connections.
    max_instruments_per_connection — maximum instrument subscriptions per
                                     single connection.
    max_depth_levels             — maximum depth levels available via streaming
                                   (None if depth streaming is not supported).
    supported_stream_modes       — set of mode names the broker accepts on this
                                   stream type, e.g. ``{"LTP", "QUOTE", "FULL"}``.
    combined_mode_caps           — Upstox-style per-mode combined limits when
                                   multiple modes are active on the same connection;
                                   mapping of mode_name -> max_instruments.
                                   None for brokers without combined caps.
    """

    max_connections: int
    max_instruments_per_connection: int
    max_depth_levels: int | None
    supported_stream_modes: frozenset[str]
    combined_mode_caps: Mapping[str, int] | None = None


# ---------------------------------------------------------------------------
# Main capability matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerCapabilities:
    """Runtime capability matrix for a single broker connection.

    Returned by ``CommonBrokerGateway.list_capabilities()`` and cached in
    ``BrokerRegistry``.  All routing and feature-gating decisions must go
    through this object — never through ``if broker_id == "dhan"`` branches.

    Boolean features
    ----------------
    supports_* flags encode whether the broker supports the named operation.
    A False value means the operation will raise UnsupportedExtensionError.

    Parameterized limits
    --------------------
    rate_limit_profiles / historical_windows / stream_limits encode per-broker
    operational envelopes that coordinators and schedulers use to make safe
    decisions.
    """

    broker_id: str

    # -- Execution --
    supports_place_order: bool = False
    supports_cancel_order: bool = False
    supports_modify_order: bool = False

    # -- Historical data --
    supports_historical_data: bool = False
    supports_intraday_history: bool = False
    supports_expired_options_history: bool = False

    # -- Live market data --
    supports_live_market_data: bool = False
    supports_depth: bool = False
    supports_depth_20_ws: bool = False
    supports_depth_200_ws: bool = False
    supports_option_chain: bool = False
    supports_polling_fallback: bool = False

    # -- Streaming --
    supports_order_stream: bool = False
    supports_portfolio_stream: bool = False

    # -- Enrichment --
    supports_news: bool = False
    supports_fundamentals: bool = False

    # -- Advanced orders --
    supports_super_order: bool = False
    supports_forever_order: bool = False
    supports_native_slice_order: bool = False

    # -- Parameterized limits --
    rate_limit_profiles: tuple[RateLimitProfile, ...] = field(default_factory=tuple)
    historical_windows: tuple[HistoricalWindowConstraint, ...] = field(default_factory=tuple)
    stream_limits: StreamLimitProfile | None = None

    # -- Classification --
    latency_class: str = "medium"  # "low" | "medium" | "high"
    reliability_class: str = "tier2"  # "tier1" | "tier2" | "tier3"

    # -- Supported vocabularies --
    product_types: frozenset[str] = field(default_factory=frozenset)
    order_types: frozenset[str] = field(default_factory=frozenset)

    # -- Batch limits --
    max_batch_size: int = 1

    # ---------------------------------------------------------------------------
    # Query helpers
    # ---------------------------------------------------------------------------

    def supports(self, feature: str) -> bool:
        """Return True if the named boolean feature is supported.

        ``feature`` should match a ``supports_*`` attribute name without the
        prefix, e.g. ``capabilities.supports("news")`` checks
        ``supports_news``.  Returns False for unknown feature names.
        """
        attr = f"supports_{feature}"
        return bool(getattr(self, attr, False))

    def limit_for(self, endpoint_class: str) -> RateLimitProfile | None:
        """Return the ``RateLimitProfile`` for the given endpoint class or None."""
        for profile in self.rate_limit_profiles:
            if profile.endpoint_class == endpoint_class:
                return profile
        return None

    def historical_window_for(self, timeframe: str) -> HistoricalWindowConstraint | None:
        """Return the ``HistoricalWindowConstraint`` for the given timeframe or None."""
        for constraint in self.historical_windows:
            if constraint.timeframe == timeframe:
                return constraint
        return None

    def can_serve_historical(self, timeframe: str, lookback_days: int) -> bool:
        """Return True if this broker can serve the given historical request."""
        if not self.supports_historical_data:
            return False
        constraint = self.historical_window_for(timeframe)
        if constraint is None:
            return False
        return lookback_days <= constraint.max_lookback_days


# ---------------------------------------------------------------------------
# CapabilityDescriptor — wraps BrokerCapabilities for registry use
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Versioned capability snapshot held in the BrokerRegistry.

    Includes the set of registered extension interface names so callers can
    discover broker-specific features without attempting to resolve them.
    """

    broker_id: str
    capabilities: BrokerCapabilities
    extensions: frozenset[str]  # registered extension type names
    observed_at: datetime

    @classmethod
    def build(
        cls,
        capabilities: BrokerCapabilities,
        extensions: frozenset[str],
    ) -> CapabilityDescriptor:
        return cls(
            broker_id=capabilities.broker_id,
            capabilities=capabilities,
            extensions=extensions,
            observed_at=datetime.now(tz=timezone.utc),
        )


# ---------------------------------------------------------------------------
# Known capability snapshots for Dhan and Upstox
# ---------------------------------------------------------------------------


def dhan_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Dhan broker.

    Values are derived from broker documentation and observed API behavior.
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
        supports_depth_200_ws=True,
        supports_option_chain=True,
        supports_polling_fallback=True,
        supports_order_stream=True,
        supports_portfolio_stream=False,
        supports_news=False,
        supports_fundamentals=False,
        supports_super_order=True,
        supports_forever_order=True,
        supports_native_slice_order=True,
        rate_limit_profiles=(
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=25.0,
                min_interval_ms=40,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="quotes",
                sustained_rps=6.0,
                min_interval_ms=167,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="historical",
                sustained_rps=6.0,
                min_interval_ms=167,
                cooldown_on_429_s=130,
            ),
            RateLimitProfile(
                endpoint_class="option_chain",
                sustained_rps=3.0,
                min_interval_ms=350,
                cooldown_on_429_s=130,
            ),
        ),
        historical_windows=(
            HistoricalWindowConstraint(
                timeframe="1m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="5m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
            ),
            HistoricalWindowConstraint(
                timeframe="15m",
                max_lookback_days=3650,
                max_chunk_days=90,
                supports_expired_instruments=True,
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
    )


def upstox_capabilities() -> BrokerCapabilities:
    """Authoritative capability snapshot for the Upstox broker.

    Values are derived from broker documentation and observed API behavior.
    """
    return BrokerCapabilities(
        broker_id="upstox",
        supports_place_order=True,
        supports_cancel_order=True,
        supports_modify_order=True,
        supports_historical_data=True,
        supports_intraday_history=True,
        supports_expired_options_history=False,
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
        supports_forever_order=True,  # via GTT adapter
        supports_native_slice_order=False,
        rate_limit_profiles=(
            RateLimitProfile(
                endpoint_class="orders",
                sustained_rps=10.0,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="quotes",
                sustained_rps=1.0,
                min_interval_ms=1000,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="historical",
                sustained_rps=5.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
            RateLimitProfile(
                endpoint_class="option_chain",
                sustained_rps=5.0,
                min_interval_ms=200,
                cooldown_on_429_s=60,
            ),
        ),
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
        stream_limits=StreamLimitProfile(
            max_connections=2,  # 5 for Plus plan
            max_instruments_per_connection=5000,
            max_depth_levels=None,  # no native depth WS; REST only
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
        max_batch_size=10,
    )
