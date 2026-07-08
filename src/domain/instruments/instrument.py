"""Instrument — pure domain object. No wrappers. No shims.

This is what a trader interacts with:

    nifty = Index("NIFTY")
    nifty.ltp
    nifty.subscribe()
    nifty.option_chain().atm.greeks.delta

The broker is never referenced here.
It lives behind the DataProvider/ExecutionProvider ports,
set at the composition root.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

import pandas as pd

logger = logging.getLogger(__name__)

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain
from domain.entities.options import OptionChain as OptionChainVO
from domain.instruments.instrument_id import InstrumentId

if TYPE_CHECKING:
    from domain.ports.protocols import DataProvider, ExecutionProvider, SubscriptionHandle


# ══════════════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class InstrumentState:
    """Immutable state snapshot. Replaced atomically on mutation."""

    quote: QuoteSnapshot | None = None
    depth: MarketDepth | None = None
    is_subscribed: bool = False
    last_tick: QuoteSnapshot | None = None
    error: str | None = None


# ══════════════════════════════════════════════════════════════════════
# Instrument (base)
# ══════════════════════════════════════════════════════════════════════


class Instrument:
    """Pure domain object. Users work with this directly.

    Owns:
        - Identity (InstrumentId)
        - State (InstrumentState) — replaced atomically

    Delegates to:
        - DataProvider for market data
        - ExecutionProvider for orders

    Does NOT own:
        - Broker connection (provider does)
        - WebSocket management (provider does)
        - Historical storage (provider does)
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        data_provider: DataProvider | None = None,
        execution_provider: ExecutionProvider | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._id = instrument_id
        self._provider = data_provider
        self._executor = execution_provider
        self._metadata = metadata or {}
        self._state = InstrumentState()
        self._subscription: SubscriptionHandle | None = None
        self._callbacks: dict[str, list[Callable]] = {
            "tick": [],
            "quote": [],
            "depth": [],
            "disconnect": [],
            "reconnect": [],
        }
        self._extensions: dict[str, Any] = {}
        self._lock = threading.RLock()  # Thread-safety for state mutations

    # ── Identity ──────────────────────────────────────────────────────

    @property
    def id(self) -> InstrumentId:
        return self._id

    @property
    def symbol(self) -> str:
        return self._id.underlying

    @property
    def exchange(self) -> str:
        return self._id.exchange

    @property
    def asset_type(self) -> str:
        return self._id.asset_type

    @property
    def lot_size(self) -> int:
        return self._metadata.get("lot_size", 1)

    @property
    def tick_size(self) -> Decimal:
        raw = self._metadata.get("tick_size")
        return Decimal(str(raw)) if raw is not None else Decimal("0.05")

    # ── Live State ────────────────────────────────────────────────────

    @property
    def quote(self) -> QuoteSnapshot | None:
        return self._state.quote

    @property
    def ltp(self) -> Decimal | None:
        q = self._state.quote
        return q.ltp if q else None

    @property
    def bid(self) -> Decimal | None:
        q = self._state.quote
        return q.bid if q else None

    @property
    def ask(self) -> Decimal | None:
        q = self._state.quote
        return q.ask if q else None

    @property
    def volume(self) -> int:
        q = self._state.quote
        return q.volume if q else 0

    @property
    def market_depth(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def order_book(self) -> MarketDepth | None:
        return self._state.depth

    @property
    def is_live(self) -> bool:
        return self._state.is_subscribed

    @property
    def last_tick(self) -> QuoteSnapshot | None:
        return self._state.last_tick

    # ── Behaviors ─────────────────────────────────────────────────────

    def refresh(self) -> QuoteSnapshot | None:
        """Pull latest quote into state."""
        if self._provider is None:
            return None
        quote = self._provider.get_quote(self._id)
        if quote is not None:
            with self._lock:
                self._state = InstrumentState(
                    quote=quote,
                    depth=self._state.depth,
                    is_subscribed=self._state.is_subscribed,
                    last_tick=self._state.last_tick,
                )
        return quote

    def history(
        self,
        *,
        timeframe: str = "1D",
        days: int = 120,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Historical OHLCV attached to this instrument."""
        if self._provider is None:
            return pd.DataFrame()
        return self._provider.get_history(
            self._id,
            timeframe=timeframe,
            lookback_days=days,
            from_date=start,
            to_date=end,
        )

    def depth(self) -> MarketDepth | None:
        """Fetch market depth."""
        if self._provider is None:
            return None
        return self._provider.get_depth(self._id)

    def spread(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return self.ask - self.bid
        return None

    def mid_price(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def statistics(self) -> dict:
        """Return current statistics snapshot."""
        q = self._state.quote
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "ltp": q.ltp if q else None,
            "bid": q.bid if q else None,
            "ask": q.ask if q else None,
            "volume": q.volume if q else 0,
            "high": q.high if q else None,
            "low": q.low if q else None,
            "open": q.open_ if q else None,
            "close": q.close if q else None,
            "spread": self.spread(),
            "mid_price": self.mid_price(),
        }

    def snapshot(self) -> dict:
        """Return full state snapshot."""
        return {
            "id": str(self._id),
            "state": {
                "quote": self._state.quote.__dict__ if self._state.quote else None,
                "depth": self._state.depth.__dict__ if self._state.depth else None,
                "is_subscribed": self._state.is_subscribed,
                "error": self._state.error,
            },
        }

    def serialize(self) -> dict:
        """JSON-serializable representation."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "lot_size": self.lot_size,
            "tick_size": str(self.tick_size),
        }

    def clone(self) -> Instrument:
        """Deep copy of this instrument."""
        return Instrument(
            self._id,
            data_provider=self._provider,
            execution_provider=self._executor,
            metadata=self._metadata.copy(),
        )

    # ── Live Data ─────────────────────────────────────────────────────

    def subscribe(
        self,
        callback: Callable[[InstrumentId, Any], None] | None = None,
        *,
        depth: bool = False,
    ) -> SubscriptionHandle | None:
        """Subscribe to live data."""
        if self._provider is None:
            return None

        def _wrapped(iid: InstrumentId, payload: Any) -> None:
            # Update state atomically
            with self._lock:
                if isinstance(payload, MarketDepth):
                    self._state = InstrumentState(
                        quote=self._state.quote,
                        depth=payload,
                        is_subscribed=True,
                        last_tick=self._state.last_tick,
                    )
                else:
                    self._state = InstrumentState(
                        quote=payload if isinstance(payload, QuoteSnapshot) else self._state.quote,
                        depth=self._state.depth,
                        is_subscribed=True,
                        last_tick=payload
                        if isinstance(payload, QuoteSnapshot)
                        else self._state.last_tick,
                    )
            # Invoke registered callbacks (outside lock to avoid deadlock)
            # Snapshot the list under lock to avoid race conditions
            with self._lock:
                tick_callbacks = list(self._callbacks.get("tick", []))
            for cb in tick_callbacks:
                try:
                    cb(payload)
                except Exception:
                    logger.exception("tick callback %r failed for %s", cb, self._id)
            # Invoke user callback
            if callback is not None:
                callback(iid, payload)

        handle = self._provider.subscribe(self._id, _wrapped, depth=depth)
        self._subscription = handle
        with self._lock:
            self._state = InstrumentState(
                quote=self._state.quote,
                depth=self._state.depth,
                is_subscribed=True,
                last_tick=self._state.last_tick,
            )
        return handle

    def unsubscribe(self) -> None:
        """Tear down live subscription."""
        if self._subscription is not None:
            self._subscription.unsubscribe()
            self._subscription = None
        with self._lock:
            self._state = InstrumentState(
                quote=self._state.quote,
                depth=self._state.depth,
                is_subscribed=False,
                last_tick=self._state.last_tick,
            )

    def on_tick(self, callback: Callable) -> None:
        """Register tick callback."""
        with self._lock:
            self._callbacks["tick"] = self._callbacks["tick"] + [callback]

    def on_quote(self, callback: Callable) -> None:
        """Register quote callback."""
        with self._lock:
            self._callbacks["quote"] = self._callbacks["quote"] + [callback]

    def on_depth(self, callback: Callable) -> None:
        """Register depth callback."""
        with self._lock:
            self._callbacks["depth"] = self._callbacks["depth"] + [callback]

    def on_disconnect(self, callback: Callable) -> None:
        """Register disconnect callback."""
        with self._lock:
            self._callbacks["disconnect"] = self._callbacks["disconnect"] + [callback]

    def on_reconnect(self, callback: Callable) -> None:
        """Register reconnect callback."""
        with self._lock:
            self._callbacks["reconnect"] = self._callbacks["reconnect"] + [callback]

    # ── Chains ────────────────────────────────────────────────────────

    def option_chain(self, expiry: date | None = None):
        """Return option chain as a rich domain object."""
        if self._provider is None:
            from domain.options.option_chain import OptionChain

            return OptionChain.empty()
        chain_vo = self._provider.get_option_chain(self._id, expiry=expiry)
        from domain.options.option_chain import OptionChain

        return OptionChain(chain_vo, provider=self._provider)

    def future_chain(self) -> FutureChain:
        """Return futures chain."""
        if self._provider is None:
            return FutureChain.empty()
        return self._provider.get_future_chain(self._id)

    # ── Orders ────────────────────────────────────────────────────────

    def _place_order(
        self,
        side: str,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
        trigger_price: Decimal | None = None,
    ):
        """Place an order (internal helper)."""
        if self._executor is None:
            raise RuntimeError("No execution provider configured")
        from domain.orders.requests import OrderRequest

        return self._executor.place_order(
            OrderRequest(
                symbol=self.symbol,
                exchange=self.exchange,
                transaction_type=side,
                quantity=quantity,
                price=price or Decimal("0"),
                order_type=order_type,
                product_type=product_type,
                trigger_price=trigger_price,
            )
        )

    def buy(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        """Place a buy order."""
        return self._place_order("BUY", quantity, price, order_type, product_type)

    def sell(
        self,
        quantity: int,
        price: Decimal | None = None,
        order_type: str = "LIMIT",
        product_type: str = "INTRADAY",
    ):
        """Place a sell order."""
        return self._place_order("SELL", quantity, price, order_type, product_type)

    def market(self, quantity: int, side: str = "BUY"):
        """Place a market order."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(side, quantity, order_type="MARKET")

    def limit(self, quantity: int, price: Decimal, side: str = "BUY"):
        """Place a limit order."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(side, quantity, price=price)

    def stop_loss(self, quantity: int, trigger_price: Decimal, side: str = "BUY"):
        """Place a stop-loss order."""
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'BUY' or 'SELL'.")
        return self._place_order(
            side.upper(), quantity, order_type="STOP_LOSS_MARKET",
            trigger_price=trigger_price,
        )

    # ── Extensions ────────────────────────────────────────────────────

    @property
    def broker(self):
        """Return broker-specific extension."""
        if self._provider is None:
            return None
        broker_id = getattr(self._provider, "name", None)
        if broker_id is None:
            return None
        return self._extensions.get(broker_id)

    @property
    def extensions(self):
        """All available broker extensions."""
        return list(self._extensions.values())

    def has_extension(self, name: str) -> bool:
        return name in self._extensions

    def get_extension(self, name: str):
        return self._extensions.get(name)

    # ── Representation ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._id})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)


# ══════════════════════════════════════════════════════════════════════
# Specialized Instruments
# ══════════════════════════════════════════════════════════════════════


class Equity(Instrument):
    """Equity instrument. ``Equity("RELIANCE")``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.equity(exchange, symbol), **kwargs)


class Index(Instrument):
    """Index instrument. ``Index("NIFTY")``."""

    def __init__(
        self,
        name: str,
        exchange: str = "NSE",
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.index(exchange, name), **kwargs)


class Future(Instrument):
    """Futures instrument. ``Future("NIFTY", expiry=date(...))``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NFO",
        *,
        expiry: date,
        **kwargs: Any,
    ) -> None:
        super().__init__(InstrumentId.future(exchange, symbol, expiry), **kwargs)
        self._expiry = expiry

    @property
    def expiry(self) -> date:
        return self._expiry

    def basis(self, spot: Decimal | None = None) -> Decimal | None:
        return None

    def cost_of_carry(self, rate: Decimal | None = None) -> Decimal | None:
        return None

    def rollover(self) -> Future | None:
        return None

    def continuous(self) -> pd.DataFrame:
        return pd.DataFrame()


class Option(Instrument):
    """Option instrument. Usually built from a chain leg.

    ``Option.from_leg(...)`` constructs one carrying its greeks/IV.
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        strike: Decimal,
        expiry: date | None,
        right: str,
        leg: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(instrument_id, **kwargs)
        self._strike = strike
        self._expiry = expiry
        self._right = right
        self._leg = leg

    @property
    def strike(self) -> Decimal:
        return self._strike

    @property
    def expiry(self) -> date | None:
        return self._expiry

    @property
    def right(self) -> str:
        return self._right

    @property
    def is_call(self) -> bool:
        return self._right == "CE"

    @property
    def is_put(self) -> bool:
        return self._right == "PE"

    @property
    def greeks(self):
        from domain.options.greeks import Greeks

        leg_greeks = getattr(self._leg, "greeks", None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()

    @property
    def iv(self):
        return getattr(self._leg, "iv", None)

    def black_scholes(self, spot: Decimal, rate: Decimal | None = None) -> Decimal | None:
        return None

    def payoff(self, spot: Decimal) -> Decimal | None:
        return None

    def intrinsic_value(self, spot: Decimal) -> Decimal | None:
        return None

    def extrinsic_value(self, spot: Decimal) -> Decimal | None:
        return None

    def moneyness(self, spot: Decimal) -> str:
        return "ATM"

    def implied_volatility(self, market_price: Decimal) -> Decimal | None:
        return None

    @classmethod
    def from_leg(
        cls,
        underlying: str,
        exchange: str,
        expiry: date | str | None,
        strike: Decimal,
        right: str,
        leg: Any,
        **kwargs: Any,
    ) -> Option:
        """Construct Option from a chain leg."""
        if isinstance(expiry, str):
            from datetime import datetime

            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                try:
                    expiry = datetime.strptime(expiry, fmt).date()
                    break
                except ValueError:
                    continue
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        return cls(iid, strike=strike, expiry=expiry, right=right, leg=leg, **kwargs)
