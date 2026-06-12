"""Trade_XV2 Broker — production-grade multi-broker trading module.

A Python trading broker module inspired by the Trade_J architecture,
featuring rate limiting, circuit breakers, retry with backoff,
capability-based connection interface, broker routing with fallback,
simulated paper trading, and real broker adapters.

Key components:
    - ``broker.core``: Enums, models, GatewayResult, BrokerConnection, schemas
    - ``broker.handle``: BrokerHandle fluent API
    - ``broker.router``: BrokerRouter with fallback routing
    - ``broker.dhan``: DhanHQ real broker adapter
    - ``broker.resilience``: Rate limiters, circuit breakers, retry executor
    - ``broker.multiplexer``: WebSocket subscription multiplexer

Usage::
    from brokers import BrokerRouter, BrokerHandle
    from brokers.common.core import OrderRequest, ExchangeSegment, TransactionType
"""

from __future__ import annotations

# Core
from brokers.common.core.auth import (
    AuthManager,
    EnvTokenStateStore,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
    TokenStateStore,
)
from brokers.common.core.connection import BrokerConnection, Capability, ConnectionStatus
from brokers.common.core.enums import (
    ExchangeSegment,
    FeedMode,
    InstrumentType,
    OrderStatus,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.instruments import Instrument, InstrumentRegistry
from brokers.common.core.models import (
    ConditionalAlert,
    ConditionalAlertRequest,
    FundLimits,
    HistoricalCandle,
    Holding,
    MarketDepth,
    MarketDepthLevel,
    ModifyOrderRequest,
    OptionContract,
    Order,
    OrderPreview,
    OrderRequest,
    OrderResponse,
    PnlExitPolicy,
    PnlExitResult,
    Position,
    Quote,
    SliceOrderRequest,
    Trade,
)
from brokers.common.core.result import GatewayResult, ResultMetadata
from brokers.common.resilience.backoff import ExponentialBackoff, FixedBackoff, NoBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from brokers.common.resilience.errors import (
    CircuitBreakerOpenError,
    NonRetryableError,
    RateLimitError,
    RetryableError,
)

# Resilience
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from brokers.common.resilience.retry import RetryConfig, RetryExecutor

# DhanHQ adapter
from brokers.dhan import DhanBroker, DhanBrokerProvider

# Gateway (ultra-simple API)
from brokers.gateway import Gateway

# Handle & Router
from brokers.handle import BrokerHandle

# WebSocket multiplexer
from brokers.multiplexer import MarketSubscriptionRequest, WebSocketMultiplexer
from brokers.router import BrokerRouter

__all__ = [
    # Auth
    "AuthManager",
    # Core connection
    "BrokerConnection",
    # Handle & Router
    "BrokerHandle",
    "BrokerRouter",
    "Capability",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "ConditionalAlert",
    "ConditionalAlertRequest",
    "ConnectionStatus",
    # Broker implementations
    "DhanBroker",
    "DhanBrokerProvider",
    "EnvTokenStateStore",
    # Enums
    "ExchangeSegment",
    "ExponentialBackoff",
    "FeedMode",
    "FixedBackoff",
    "FundLimits",
    # Gateway
    "Gateway",
    # Result
    "GatewayResult",
    "HistoricalCandle",
    "Holding",
    # Instruments
    "Instrument",
    "InstrumentRegistry",
    "InstrumentType",
    "JsonTokenStateStore",
    "MarketDepth",
    "MarketDepthLevel",
    "MarketSubscriptionRequest",
    "ModifyOrderRequest",
    "MultiBucketRateLimiter",
    "NoBackoff",
    "NonRetryableError",
    "OptionContract",
    # Models
    "Order",
    "OrderPreview",
    "OrderRequest",
    "OrderResponse",
    "OrderStatus",
    "OrderType",
    "PnlExitPolicy",
    "PnlExitResult",
    "Position",
    "ProductType",
    "Quote",
    "RateLimitConfig",
    "RateLimitError",
    "ResultMetadata",
    "RetryConfig",
    "RetryExecutor",
    "RetryableError",
    "SliceOrderRequest",
    # Resilience
    "TokenBucketRateLimiter",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "Trade",
    "TransactionType",
    "Validity",
    "WebSocketMultiplexer",
]
