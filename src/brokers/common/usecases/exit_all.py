"""exit_all use case."""

from __future__ import annotations

from typing import Any, Protocol


class ExitAllStrategy(Protocol):
    def exit_all(self) -> dict[str, Any]: ...


def exit_all(strategy: ExitAllStrategy) -> dict[str, Any]:
    """Close all positions / cancel open orders via the broker strategy."""
    return strategy.exit_all()


__all__ = ["ExitAllStrategy", "exit_all"]
