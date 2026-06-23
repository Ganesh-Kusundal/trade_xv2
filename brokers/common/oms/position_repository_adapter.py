"""Position repository adapter."""

from __future__ import annotations

from domain import Position
from domain.repositories import PositionRepository
from brokers.common.oms.position_manager import PositionManager


class PositionManagerRepository:
    def __init__(self, position_manager: PositionManager) -> None:
        self._pm = position_manager

    def get_positions(self) -> list[Position]:
        return self._pm.get_positions()


__all__ = ["PositionManagerRepository"]
