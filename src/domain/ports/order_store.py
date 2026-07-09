"""Order store port — application boundary for durable order persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.entities.order import Order


@runtime_checkable
class OrderStorePort(Protocol):
    """Application boundary for the durable order store.

    The OMS depends on this port; the concrete ``SqliteOrderStore`` is
    injected by a composition root (cli / api / brokers.common), never
    constructed inside ``application``.
    """

    def upsert(self, order: Order) -> None: ...

    def load_all(self) -> list[Order]: ...

    def close(self) -> None: ...
