"""place_bracket / cancel_bracket use cases."""

from __future__ import annotations

from typing import Any, Protocol


class BracketStrategy(Protocol):
    def place_bracket(self, **kwargs: Any) -> Any: ...

    def cancel_bracket(self, order_id: str) -> Any: ...


def place_bracket(strategy: BracketStrategy, **kwargs: Any) -> Any:
    return strategy.place_bracket(**kwargs)


def cancel_bracket(strategy: BracketStrategy, order_id: str) -> Any:
    return strategy.cancel_bracket(order_id)


__all__ = ["BracketStrategy", "cancel_bracket", "place_bracket"]
