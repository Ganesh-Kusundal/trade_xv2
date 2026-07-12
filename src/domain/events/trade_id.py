"""TradeIdKey — canonical identifier for a trade.

Split from ``types.py`` (ADR-010) to reduce file size while maintaining
backward compatibility via re-exports in ``types.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeIdKey:
    """Canonical identifier for a trade.

    Two trades are considered the same if and only if their
    :class:`TradeIdKey` compares equal.
    """

    trade_id: str
    broker_trade_id: str | None = None
    order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.trade_id:
            raise ValueError("TradeIdKey requires a non-empty trade_id")
        object.__setattr__(self, "trade_id", str(self.trade_id).strip())
        if self.broker_trade_id is not None:
            object.__setattr__(self, "broker_trade_id", str(self.broker_trade_id).strip())
        if self.order_id is not None:
            object.__setattr__(self, "order_id", str(self.order_id).strip())

    @classmethod
    def from_trade(cls, trade: Any) -> TradeIdKey:
        """Build a key from a domain ``Trade`` (or any duck-typed object)."""
        trade_id = getattr(trade, "trade_id", "") or ""
        broker_trade_id = (
            getattr(trade, "broker_trade_id", None)
            or getattr(trade, "exchange_trade_id", None)
            or None
        )
        order_id = getattr(trade, "order_id", None) or None
        return cls(
            trade_id=trade_id,
            broker_trade_id=broker_trade_id,
            order_id=order_id,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> TradeIdKey:
        """Build a key from a raw event payload ``{"trade": Trade(...)}``."""
        trade = payload.get("trade")
        if trade is not None:
            return cls.from_trade(trade)
        return cls(
            trade_id=str(payload.get("trade_id", "")),
            broker_trade_id=payload.get("broker_trade_id"),
            order_id=payload.get("order_id"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "trade_id": self.trade_id,
            "broker_trade_id": self.broker_trade_id,
            "order_id": self.order_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TradeIdKey:
        return cls(
            trade_id=str(raw.get("trade_id", "")),
            broker_trade_id=raw.get("broker_trade_id"),
            order_id=raw.get("order_id"),
        )
