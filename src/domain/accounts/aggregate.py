"""Re-export AccountAggregate from the canonical aggregates module."""

from domain.aggregates.account import AccountAggregate

__all__ = ["AccountAggregate"]
