"""Risk manager port for datalake API."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RiskManagerPort(Protocol):
    def get_status(self) -> dict[str, Any]:
        ...

    def is_kill_switch_active(self) -> bool:
        ...


__all__ = ["RiskManagerPort"]
