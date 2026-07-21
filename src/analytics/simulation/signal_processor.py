"""SignalProcessor — shared signal-to-fill engine for paper and replay (REF-5).

Both engines share the same shape: check actionability, route through OMS
when available (booking the OMS-resolved, slipped-once fill price) or
simulate a fill directly otherwise. What differs between paper and replay —
position/trade record shapes, capital bookkeeping, entry gating, and sizing
— is supplied via :class:`SignalProcessorHooks` so each mode's adapter
(``analytics.paper.signal_processor``, ``analytics.replay.signal_processor``)
stays a thin, explicit configuration of this one engine.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import Side
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort

logger = logging.getLogger(__name__)


@dataclass
class SignalProcessorHooks:
    """Mode-specific collaborators the shared :class:`SignalProcessor` delegates to.

    ``book_buy_fill``/``book_sell_fill`` own the part that genuinely differs
    per mode: commission, cash/ledger update, trade-record construction and
    append, position marking, and fill recording. The engine owns what is
    identical: actionability/gating checks, quantity sizing dispatch, and the
    OMS open/close + once-only-slippage routing.
    """

    equity_for_sizing: Callable[[Any], float]
    position_view: Callable[[Any, str], Any | None]
    slippage_pct: Callable[[Any, HistoricalBar], float]
    size_for_simulated: Callable[[Any, float, float], int]
    size_for_oms: Callable[[Any, float, float], int]
    entry_gate: Callable[..., bool]  # (session, config, *, via_oms, symbol) -> blocked?
    oms_slippage_pct: Callable[[Any], float]
    buy_order_meta: Callable[[Signal], tuple[str, list[str]]]
    sell_order_meta: Callable[[Signal, Any], tuple[str, list[str]]]
    book_buy_fill: Callable[..., None]
    book_sell_fill: Callable[..., None]


class SignalProcessor:
    """Process trade signals into simulated or OMS-routed fills.

    Parameters
    ----------
    hooks:
        Mode-specific collaborators (see :class:`SignalProcessorHooks`).
    oms_adapter:
        Optional OMS backtest adapter. When ``None``, fills are simulated
        directly (pure backtest / research mode).
    on_sync:
        Optional callback invoked after an OMS-routed sell to resync session
        capital from a portfolio tracker.
    """

    def __init__(
        self,
        hooks: SignalProcessorHooks,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        on_sync: Callable[[Any], None] | None = None,
    ) -> None:
        self._hooks = hooks
        self._oms_adapter = oms_adapter
        self._on_sync = on_sync

    def process(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: Any,
        config: Any = None,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Process a signal for order execution.

        Routes through OMS when available (backtest-live parity). Falls
        back to direct simulation when no OMS adapter is configured.
        """
        if not signal.is_actionable:
            return

        if self._oms_adapter is not None:
            self._process_via_oms(signal, bar, session, config, fill_price=fill_price)
        else:
            self._process_simulated(signal, bar, session, config, fill_price=fill_price)

    # ------------------------------------------------------------------
    # Pure-simulate path
    # ------------------------------------------------------------------

    def _process_simulated(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: Any,
        config: Any = None,
        *,
        fill_price: float | None = None,
    ) -> None:
        h = self._hooks
        base_price = float(fill_price if fill_price is not None else bar.close)

        if signal.is_buy and not session.has_position(bar.symbol):
            if h.entry_gate(session, config, via_oms=False, symbol=bar.symbol):
                return
            slippage_pct = h.slippage_pct(session, bar)
            price = base_price * (1 + slippage_pct / 100)
            qty = h.size_for_simulated(session, price, h.equity_for_sizing(session))
            if qty <= 0:
                return
            h.book_buy_fill(
                session,
                bar,
                signal,
                price=price,
                base_price=base_price,
                quantity=qty,
                order_id=f"sim-open:{bar.symbol}:{session.bar_count}",
                via_oms=False,
            )
        elif signal.is_sell and session.has_position(bar.symbol):
            view = h.position_view(session, bar.symbol)
            if view is None or view.quantity <= 0:
                return
            slippage_pct = h.slippage_pct(session, bar)
            price = base_price * (1 - slippage_pct / 100)
            h.book_sell_fill(
                session,
                bar,
                signal,
                view,
                price=price,
                base_price=base_price,
                order_id=f"sim-close:{bar.symbol}:{session.bar_count}",
                via_oms=False,
            )
            session.clear_position(bar.symbol)

    # ------------------------------------------------------------------
    # OMS-backed path
    # ------------------------------------------------------------------

    def _process_via_oms(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: Any,
        config: Any = None,
        *,
        fill_price: float | None = None,
    ) -> None:
        h = self._hooks
        base_price = float(fill_price if fill_price is not None else bar.close)

        if signal.is_buy and not session.has_position(bar.symbol):
            if h.entry_gate(session, config, via_oms=True, symbol=bar.symbol):
                return
            # Un-slipped base — OmsBacktestAdapter applies slippage once (F2a).
            price = Decimal(str(base_price))
            qty = h.size_for_oms(session, float(price), h.equity_for_sizing(session))
            if qty <= 0:
                return
            strategy, reasons = h.buy_order_meta(signal)
            order_id = self._oms_adapter.open_long(
                symbol=bar.symbol,
                exchange=DEFAULT_EXCHANGE,
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=strategy,
                reasons=reasons,
            )
            if not order_id:
                return
            fill_px = resolve_oms_fill_price(
                self._oms_adapter,
                order_id,
                base_price=price,
                side=Side.BUY,
                slippage_pct=h.oms_slippage_pct(config),
            )
            h.book_buy_fill(
                session,
                bar,
                signal,
                price=fill_px,
                base_price=base_price,
                quantity=qty,
                order_id=order_id,
                via_oms=True,
            )
            if self._on_sync is not None:
                self._on_sync(session)
        elif signal.is_sell and session.has_position(bar.symbol):
            view = h.position_view(session, bar.symbol)
            if view is None or view.quantity <= 0:
                return
            price = Decimal(str(base_price))
            strategy, reasons = h.sell_order_meta(signal, view)
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange=DEFAULT_EXCHANGE,
                quantity=view.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=strategy,
                reasons=reasons,
            )
            if not order_id:
                return
            fill_px = resolve_oms_fill_price(
                self._oms_adapter,
                order_id,
                base_price=price,
                side=Side.SELL,
                slippage_pct=h.oms_slippage_pct(config),
            )
            h.book_sell_fill(
                session,
                bar,
                signal,
                view,
                price=fill_px,
                base_price=base_price,
                order_id=order_id,
                via_oms=True,
            )
            session.clear_position(bar.symbol)
            if self._on_sync is not None:
                self._on_sync(session)
