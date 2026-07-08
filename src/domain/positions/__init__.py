"""Position domain — re-exports PositionAggregate from the aggregates layer."""

from __future__ import annotations

from domain.aggregates.position import PositionAggregate

__all__ = ["PositionAggregate"]
