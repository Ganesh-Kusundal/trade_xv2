"""Market data domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from domain.candles.historical import InstrumentRef
from domain.provenance import DataProvenance


class DepthKind(str, Enum):
    """Describes the source and depth level of market depth data.

    REST_5   — 5-level depth from REST API (standard across all brokers).
    WS_20    — 20-level depth from WebSocket (Dhan-specific).
    WS_200   — 200-level depth from WebSocket (Dhan-specific, premium tier).
    """

    REST_5 = "REST_5"
    WS_20 = "WS_20"
    WS_200 = "WS_200"


@dataclass(slots=True, frozen=True)
class DepthLevel:
    """Single price level in market depth."""

    price: Decimal = Decimal("0")
    quantity: int = 0
    orders: int = 0


@dataclass(slots=True, frozen=False)
class MarketDepth:
    """Canonical market depth — bid/ask ladder.

    Kept as ``frozen=False`` because ``bids``/``asks`` are mutable lists
    that are built incrementally by broker adapters.
    """

    symbol: str = ""
    bids: list[DepthLevel] | None = None
    asks: list[DepthLevel] | None = None
    timestamp: datetime | None = None
    depth_type: str = "DEPTH_5"  # DEPTH_5, DEPTH_20, DEPTH_200

    def __post_init__(self) -> None:
        if self.bids is None:
            self.bids = []
        if self.asks is None:
            self.asks = []

    # ── Accessors ──────────────────────────────────────────────────

    @property
    def best_bid(self) -> DepthLevel | None:
        """Highest bid price level, or None if no bids."""
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> DepthLevel | None:
        """Lowest ask price level, or None if no asks."""
        return self.asks[0] if self.asks else None

    @property
    def bid_volume(self) -> int:
        """Total bid quantity across all visible levels."""
        return sum(level.quantity for level in self.bids)

    @property
    def ask_volume(self) -> int:
        """Total ask quantity across all visible levels."""
        return sum(level.quantity for level in self.asks)

    # ── Derived computations ───────────────────────────────────────

    def spread(self) -> Decimal | None:
        """Bid-ask spread. None if either side is empty."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is not None and ba is not None:
            return ba.price - bb.price
        return None

    def mid_price(self) -> Decimal | None:
        """Midpoint between best bid and best ask."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is not None and ba is not None:
            return (bb.price + ba.price) / 2
        return None

    def micro_price(self) -> Decimal | None:
        """Volume-weighted midpoint — more accurate when sizes are imbalanced."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is None or ba is None:
            return None
        bv = bb.quantity
        av = ba.quantity
        total = bv + av
        if total == 0:
            return self.mid_price()
        return (ba.price * bv + bb.price * av) / Decimal(total)

    def imbalance(self) -> Decimal | None:
        """Order-book imbalance: (bid_vol - ask_vol) / (bid_vol + ask_vol).
        Returns value in [-1, 1]. Positive = buying pressure."""
        bv = Decimal(self.bid_volume)
        av = Decimal(self.ask_volume)
        total = bv + av
        if total == 0:
            return None
        return (bv - av) / total

    def weighted_bid(self, levels: int | None = None) -> Decimal | None:
        """Volume-weighted average bid price across visible levels."""
        subset = self.bids[:levels] if levels else self.bids
        total_qty = sum(l.quantity for l in subset)
        if total_qty == 0:
            return None
        return sum(l.price * l.quantity for l in subset) / Decimal(total_qty)

    def weighted_ask(self, levels: int | None = None) -> Decimal | None:
        """Volume-weighted average ask price across visible levels."""
        subset = self.asks[:levels] if levels else self.asks
        total_qty = sum(l.quantity for l in subset)
        if total_qty == 0:
            return None
        return sum(l.price * l.quantity for l in subset) / Decimal(total_qty)

    def cumulative_depth(self) -> dict[str, list[tuple[Decimal, int]]]:
        """Cumulative bid/ask depth as sorted lists of (price, cumulative_qty)."""
        cum_bids: list[tuple[Decimal, int]] = []
        running = 0
        for level in self.bids:
            running += level.quantity
            cum_bids.append((level.price, running))
        cum_asks: list[tuple[Decimal, int]] = []
        running = 0
        for level in self.asks:
            running += level.quantity
            cum_asks.append((level.price, running))
        return {"bids": cum_bids, "asks": cum_asks}

    def level(self, n: int) -> tuple[DepthLevel | None, DepthLevel | None]:
        """Return the n-th level (0-based) as (bid_level, ask_level)."""
        bid = self.bids[n] if n < len(self.bids) else None
        ask = self.asks[n] if n < len(self.asks) else None
        return (bid, ask)

    def snapshot(self) -> dict:
        """JSON-serializable snapshot of current depth state."""
        return {
            "symbol": self.symbol,
            "best_bid": str(self.best_bid.price) if self.best_bid else None,
            "best_ask": str(self.best_ask.price) if self.best_ask else None,
            "spread": str(self.spread()) if self.spread() else None,
            "mid_price": str(self.mid_price()) if self.mid_price() else None,
            "bid_volume": self.bid_volume,
            "ask_volume": self.ask_volume,
            "levels": len(self.bids),
            "depth_type": self.depth_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def supports_levels(self, n: int) -> bool:
        """True if both sides have at least n levels."""
        return len(self.bids) >= n and len(self.asks) >= n


@dataclass(slots=True, frozen=True)
class Quote:
    """Wire/transport quote DTO — returned by ``BrokerAdapter.quote`` only.

    Product surfaces (``DataProvider``, ``Instrument``, CLI, API) must use
    :class:`QuoteSnapshot`. Convert at the provider boundary via
    :meth:`to_snapshot`.
    """

    symbol: str
    ltp: Decimal = Decimal("0")
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")  # absolute price change from previous close
    oi: int = 0  # open interest — populated for derivatives, 0 for equity
    bid: Decimal | None = None
    ask: Decimal | None = None
    timestamp: datetime | None = None

    # ── Derived computations ───────────────────────────────────────

    def spread(self) -> Decimal | None:
        """Bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid(self) -> Decimal | None:
        """Midpoint price."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def change_pct(self) -> Decimal | None:
        """Percentage change from previous close."""
        if self.close and self.close != 0:
            return (self.change / self.close) * Decimal("100")
        return None

    def is_valid(self) -> bool:
        """True if the quote has meaningful data (non-zero LTP)."""
        return self.ltp != Decimal("0")

    def is_stale(self, max_age_seconds: float = 60.0) -> bool:
        """True if the quote is older than max_age_seconds."""
        if self.timestamp is None:
            return True
        from domain.ports.time_service import get_current_clock

        now = get_current_clock().now()
        ts = (
            self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=timezone.utc)
        )
        return (now - ts).total_seconds() > max_age_seconds

    def age(self) -> float | None:
        """Age in seconds since timestamp. None if no timestamp."""
        if self.timestamp is None:
            return None
        from domain.ports.time_service import get_current_clock

        now = get_current_clock().now()
        ts = (
            self.timestamp if self.timestamp.tzinfo else self.timestamp.replace(tzinfo=timezone.utc)
        )
        return (now - ts).total_seconds()

    def snapshot(self) -> dict:
        """JSON-serializable dict."""
        return {
            "symbol": self.symbol,
            "ltp": str(self.ltp),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "change": str(self.change),
            "oi": self.oi,
            "bid": str(self.bid) if self.bid else None,
            "ask": str(self.ask) if self.ask else None,
            "spread": str(self.spread()) if self.spread() else None,
            "mid": str(self.mid()) if self.mid() else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    @property
    def market_status(self) -> str:
        """Infer market status from quote characteristics."""
        if self.volume == 0 and self.change == Decimal("0"):
            return "CLOSED"
        if self.timestamp is None:
            return "UNKNOWN"
        return "OPEN"

    def to_snapshot(
        self,
        provenance: DataProvenance | None = None,
        *,
        exchange: str = "",
        instrument: InstrumentRef | None = None,
    ) -> QuoteSnapshot:
        """Bridge: wire ``Quote`` → product ``QuoteSnapshot`` (single conversion site)."""
        from domain.ports.time_service import get_current_clock

        prov = provenance or DataProvenance.now("bridge", "quote-to-snapshot")
        pct = self.change_pct()
        return QuoteSnapshot(
            instrument=instrument or InstrumentRef(symbol=self.symbol, exchange=exchange),
            ltp=self.ltp,
            event_time=self.timestamp or get_current_clock().now(),
            provenance=prov,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            change_pct=pct if pct is not None else Decimal("0"),
            oi=self.oi,
            bid=self.bid,
            ask=self.ask,
        )


@dataclass(slots=True, frozen=True)
class MarketTick:
    """Normalized market data tick — delivered by StreamOrchestrator to consumers.

    Every tick carries full provenance so consumers can trace data lineage.
    """

    instrument: InstrumentRef
    ltp: Decimal
    event_time: datetime
    provenance: DataProvenance
    volume: int = 0
    bid: Decimal | None = None
    ask: Decimal | None = None
    sequence: int | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    broker_id: str = ""
    session_id: str = ""


@dataclass(slots=True, frozen=True)
class QuoteSnapshot:
    """Product-facing quote with provenance — sole type above the wire boundary.

    Returned by ``DataProvider.get_quote``, ``Instrument.refresh``, and
    ``brokers.services.get_quote``. Wire adapters emit :class:`Quote` and
    convert via :meth:`Quote.to_snapshot`. Time field is ``event_time``
    (not ``timestamp``); change is ``change_pct`` (not absolute ``change``).
    """

    instrument: InstrumentRef
    ltp: Decimal
    event_time: datetime
    provenance: DataProvenance
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change_pct: Decimal = Decimal("0")
    oi: int = 0  # open interest — populated for derivatives, 0 for equity
    bid: Decimal | None = None
    ask: Decimal | None = None

    # ── Derived computations ───────────────────────────────────────

    def spread(self) -> Decimal | None:
        """Bid-ask spread."""
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid(self) -> Decimal | None:
        """Midpoint price."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def is_valid(self) -> bool:
        """True if the quote has meaningful data."""
        return self.ltp != Decimal("0")

    def is_stale(self, max_age_seconds: float = 60.0) -> bool:
        """True if the event_time is older than max_age_seconds."""
        from domain.ports.time_service import get_current_clock

        now = get_current_clock().now()
        et = (
            self.event_time
            if self.event_time.tzinfo
            else self.event_time.replace(tzinfo=timezone.utc)
        )
        return (now - et).total_seconds() > max_age_seconds

    def age(self) -> float:
        """Age in seconds since event_time."""
        from domain.ports.time_service import get_current_clock

        now = get_current_clock().now()
        et = (
            self.event_time
            if self.event_time.tzinfo
            else self.event_time.replace(tzinfo=timezone.utc)
        )
        return (now - et).total_seconds()

    def snapshot(self) -> dict:
        """JSON-serializable dict."""
        return {
            "instrument": str(self.instrument),
            "ltp": str(self.ltp),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "change_pct": str(self.change_pct),
            "oi": self.oi,
            "bid": str(self.bid) if self.bid else None,
            "ask": str(self.ask) if self.ask else None,
            "spread": str(self.spread()) if self.spread() else None,
            "mid": str(self.mid()) if self.mid() else None,
            "event_time": self.event_time.isoformat(),
            "source": str(self.provenance.source),
        }

    @property
    def market_status(self) -> str:
        """Infer market status from quote characteristics."""
        if self.volume == 0 and self.change_pct == Decimal("0"):
            return "CLOSED"
        return "OPEN"

    def to_quote(self) -> Quote:
        """Bridge: product snapshot → wire Quote (loses provenance)."""
        abs_change = (
            (self.change_pct / Decimal("100")) * self.close
            if self.close
            else Decimal("0")
        )
        return Quote(
            symbol=self.instrument.symbol if self.instrument else "",
            ltp=self.ltp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            change=abs_change,
            oi=self.oi,
            bid=self.bid,
            ask=self.ask,
            timestamp=self.event_time,
        )
