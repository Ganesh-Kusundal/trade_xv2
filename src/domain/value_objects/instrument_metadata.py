"""InstrumentMetadata — structured value object for instrument configuration.

Replaces the untyped dict currently stored in Instrument._metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from domain.constants.market import DEFAULT_TICK_SIZE
from domain.market.hours import NSE_EQUITY_CLOSE, NSE_EQUITY_OPEN


@dataclass(frozen=True, slots=True)
class TradingHours:
    """Exchange trading hours for a specific session."""

    open: time = NSE_EQUITY_OPEN
    close: time = NSE_EQUITY_CLOSE
    timezone: str = "Asia/Kolkata"

    def is_within(self, check_time: time) -> bool:
        """True if check_time falls within trading hours."""
        return self.open <= check_time <= self.close


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """A scheduled corporate action."""

    action_type: str  # "DIVIDEND", "SPLIT", "BONUS", "RIGHTS"
    ex_date: str      # YYYY-MM-DD
    value: Decimal = Decimal("0")
    description: str = ""


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    """Structured instrument configuration — Value Object.

    Replaces the untyped dict[str, Any] in Instrument._metadata.
    Immutable after construction.
    """

    exchange: str = "NSE"
    lot_size: int = 1
    tick_size: Decimal = DEFAULT_TICK_SIZE
    freeze_quantity: int | None = None
    canonical_symbol: str = ""
    trading_hours: TradingHours = field(default_factory=TradingHours)
    corporate_actions: tuple[CorporateAction, ...] = ()
    isin: str = ""
    segment: str = "EQ"

    def __post_init__(self) -> None:
        if isinstance(self.tick_size, float):
            object.__setattr__(self, "tick_size", Decimal(str(self.tick_size)))
        if self.lot_size < 1:
            raise ValueError(f"lot_size must be >= 1, got {self.lot_size}")
        if self.tick_size <= Decimal("0"):
            raise ValueError(f"tick_size must be positive, got {self.tick_size}")

    @classmethod
    def from_dict(cls, data: dict) -> InstrumentMetadata:
        """Construct from the untyped dict currently used by Instrument."""
        trading_hours = TradingHours()
        if "trading_hours" in data and isinstance(data["trading_hours"], dict):
            th = data["trading_hours"]
            trading_hours = TradingHours(
                open=time.fromisoformat(th.get("open", "09:15:00")),
                close=time.fromisoformat(th.get("close", "15:30:00")),
                timezone=th.get("timezone", "Asia/Kolkata"),
            )
        corporate_actions: tuple[CorporateAction, ...] = ()
        if "corporate_actions" in data and isinstance(data["corporate_actions"], list):
            corporate_actions = tuple(
                CorporateAction(
                    action_type=ca.get("action_type", ""),
                    ex_date=ca.get("ex_date", ""),
                    value=Decimal(str(ca.get("value", "0"))),
                    description=ca.get("description", ""),
                )
                for ca in data["corporate_actions"]
                if isinstance(ca, dict)
            )
        return cls(
            exchange=data.get("exchange", "NSE"),
            lot_size=int(data.get("lot_size", 1)),
            tick_size=Decimal(str(data.get("tick_size", str(DEFAULT_TICK_SIZE)))),
            freeze_quantity=data.get("freeze_quantity"),
            canonical_symbol=data.get("canonical_symbol", data.get("symbol", "")),
            trading_hours=trading_hours,
            corporate_actions=corporate_actions,
            isin=data.get("isin", ""),
            segment=data.get("segment", "EQ"),
        )

    def to_dict(self) -> dict:
        """Serialize back to dict for backward compat with Instrument._metadata."""
        return {
            "exchange": self.exchange,
            "lot_size": self.lot_size,
            "tick_size": str(self.tick_size),
            "freeze_quantity": self.freeze_quantity,
            "canonical_symbol": self.canonical_symbol,
            "isin": self.isin,
            "segment": self.segment,
        }
