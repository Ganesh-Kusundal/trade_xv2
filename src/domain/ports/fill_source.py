"""FillSource port — order submission and cancellation interface."""

from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    success: bool
    message: str = ""


@dataclass(frozen=True)
class CancelResult:
    success: bool
    message: str = ""


@runtime_checkable
class FillSource(Protocol):
    def submit(self, command: object) -> OrderResult: ...
    def cancel(self, order_id: str) -> CancelResult: ...
