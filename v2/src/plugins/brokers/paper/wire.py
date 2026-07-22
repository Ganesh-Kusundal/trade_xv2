"""Paper wire — domain ↔ domain identity (no venue-native payload)."""

from __future__ import annotations

from domain.entities import Order, Position, Quote
from plugins.brokers.common.wire import BaseWireAdapter


class PaperWire(BaseWireAdapter):
    def to_quote(self, native: Quote) -> Quote:
        return native

    def from_quote(self, domain: Quote) -> Quote:
        return domain

    def to_order(self, native: Order) -> Order:
        return native

    def from_order(self, domain: Order) -> Order:
        return domain

    def to_position(self, native: Position) -> Position:
        return native

    def from_position(self, domain: Position) -> Position:
        return domain
