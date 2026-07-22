"""BrokerAdapter port — unified broker interface for data + execution."""

from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    success: bool
    message: str = ""


@dataclass(frozen=True)
class BrokerSnapshot:
    orders: tuple
    positions: tuple
    funds: object


@runtime_checkable
class BrokerAdapter(Protocol):
    broker_id: str
    is_connected: bool

    def connect(self) -> bool: ...
    def disconnect(self) -> None: ...
    def place_order(self, command: object) -> OrderResult: ...
    def cancel_order(self, order_id: str) -> OrderResult: ...
    def get_quote(self, instrument_id: object) -> object: ...
    def get_positions(self) -> list: ...
    def get_funds(self) -> object: ...
    def mass_status(self) -> BrokerSnapshot: ...
    def load_instruments(self) -> None: ...
    def capabilities(self) -> object: ...
