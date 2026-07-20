"""Backward-compatible re-export — use infrastructure.resilience.backoff."""

from infrastructure.resilience.backoff import exponential_backoff_seconds as exponential_backoff

__all__ = ["exponential_backoff"]
