"""Compatibility re-export — prefer ``brokers.dhan.resilience.retry_policies``.

Historical import path ``brokers.dhan.resilience.retry_executor`` remains for
tests and callers. There is no second RetryExecutor implementation; all
execution uses ``infrastructure.resilience.retry_executor.RetryExecutor``.
"""

from __future__ import annotations

from brokers.dhan.resilience.retry_policies import (  # noqa: F401
    ADMIN_POLICY,
    DhanRetryExecutorFactory,
    DhanRetryPolicy,
    MARKET_DATA_POLICY,
    ORDERS_POLICY,
    PORTFOLIO_POLICY,
    build_retry_executor,
    create_retry_executor,
)

__all__ = [
    "ADMIN_POLICY",
    "DhanRetryExecutorFactory",
    "DhanRetryPolicy",
    "MARKET_DATA_POLICY",
    "ORDERS_POLICY",
    "PORTFOLIO_POLICY",
    "build_retry_executor",
    "create_retry_executor",
]
