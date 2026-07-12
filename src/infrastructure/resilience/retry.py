"""Deprecated shim — RetryExecutor now lives in ``infrastructure.resilience.retry_executor``.

The single authority for retry execution is
:class:`infrastructure.resilience.retry_executor.RetryExecutor`. Import
``RetryConfig`` / ``RetryExecutor`` from ``infrastructure.resilience.retry_executor``
instead of this module. This shim exists only for backward compatibility and
will be removed.
"""

from __future__ import annotations

from infrastructure.resilience.retry_executor import (
    DEFAULT_RETRYABLE_EXCEPTIONS,
    RetryConfig,
    RetryExecutor,
)

__all__ = ["DEFAULT_RETRYABLE_EXCEPTIONS", "RetryConfig", "RetryExecutor"]
