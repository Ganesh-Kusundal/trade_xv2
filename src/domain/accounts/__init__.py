"""Account domain — re-exports AccountAggregate from the aggregates layer."""

from __future__ import annotations

from domain.aggregates.account import AccountAggregate

__all__ = ["AccountAggregate"]
