"""GTT use cases."""

from __future__ import annotations

from typing import Any, Protocol


class GttStrategy(Protocol):
    def place_gtt(self, **kwargs: Any) -> Any: ...

    def cancel_gtt(self, gtt_id: str) -> Any: ...


def place_gtt(strategy: GttStrategy, **kwargs: Any) -> Any:
    return strategy.place_gtt(**kwargs)


def cancel_gtt(strategy: GttStrategy, gtt_id: str) -> Any:
    return strategy.cancel_gtt(gtt_id)


__all__ = ["GttStrategy", "cancel_gtt", "place_gtt"]
