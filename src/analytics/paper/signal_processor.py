"""Signal processing for paper trading — thin adapter over the shared engine.

Configures :class:`analytics.simulation.signal_processor.SignalProcessor`
with paper-specific hooks (REF-5): cash callback, ``PaperTrade`` records,
capital-based sizing, and the max-positions / daily-loss entry gates.
Slippage is applied **once** inside ``OmsBacktestAdapter`` (same as replay)
— this module passes the un-slipped base price.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from analytics.paper.models import PaperSession, PaperTrade
from analytics.simulation.signal_processor import SignalProcessor, SignalProcessorHooks
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import Side
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from application.services.simulation_orchestrator import PositionMeta
from application.services.trading_costs_service import compute_commission

logger = logging.getLogger(__name__)


class PaperSignalProcessor:
    """Process paper trading signals through the OMS for live parity.

    Parameters
    ----------
    config:
        Paper trading configuration (capital, slippage, position limits, etc.).
    oms_adapter:
        Adapter used to open/close simulated positions. Required.
    record_fill:
        Callback ``record_fill(session, *, order_id, symbol, exchange, side,
        quantity, price, timestamp, trade_tag) -> bool`` supplied by the engine
        to apply a fill to the session's portfolio.
    on_cash:
        Optional ``(session, delta)`` cash applicator (ledger when wired).
    """

    def __init__(
        self,
        config,
        record_fill,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        on_cash: Callable[[PaperSession, float], None] | None = None,
    ) -> None:
        self._config = config
        self._record_fill = record_fill
        self._on_cash = on_cash
        self._impl = SignalProcessor(self._build_hooks(), oms_adapter=oms_adapter)

    def _apply_cash(self, session: PaperSession, delta: float) -> None:
        if self._on_cash is not None:
            self._on_cash(session, delta)
        else:
            session.capital += delta

    def _commission(self, notional: float, side: Side) -> float:
        cfg = self._config
        return compute_commission(
            notional,
            side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def _entry_gate(self, session, config, *, via_oms: bool, symbol: str) -> bool:
        cfg = self._config
        if session.position_count >= cfg.max_positions:
            return True
        if via_oms and cfg.max_daily_loss_pct > 0:
            from domain.risk.policy import check_paper_daily_loss

            loss_check = check_paper_daily_loss(
                session.daily_pnl, session.total_equity, cfg.max_daily_loss_pct
            )
            if not loss_check.approved:
                logger.info(
                    "paper_daily_loss_blocked",
                    extra={"reason": loss_check.reason, "symbol": symbol},
                )
                return True
        return False

    def _size_for_simulated(self, session, price: float, equity: float) -> int:
        cfg = self._config
        qty = compute_order_quantity(equity=equity, price=price, max_position_pct=cfg.max_position_pct)
        if qty <= 0:
            return 0
        commission = self._commission(price * qty, Side.BUY)
        if price * qty + commission > equity:
            return 0
        return qty

    def _size_for_oms(self, session, price: float, equity: float) -> int:
        cfg = self._config
        return compute_order_quantity(equity=equity, price=price, max_position_pct=cfg.max_position_pct)

    def _book_buy_fill(
        self,
        session: PaperSession,
        bar: HistoricalBar,
        signal: Signal,
        *,
        price: float,
        base_price: float,
        quantity: int,
        order_id: str,
        via_oms: bool,
    ) -> None:
        commission = self._commission(price * quantity, Side.BUY)
        self._apply_cash(session, -(price * quantity + commission))
        self._record_fill(
            session,
            order_id=order_id,
            symbol=bar.symbol,
            exchange=DEFAULT_EXCHANGE,
            side=Side.BUY,
            quantity=quantity,
            price=price,
            timestamp=bar.timestamp,
            trade_tag="open",
        )
        session.mark_symbol(bar.symbol, bar.close)
        session.position_meta[bar.symbol] = PositionMeta(
            entry_time=bar.timestamp,
            stop_loss=signal.stop_loss,
            target=signal.target,
            strategy=signal.strategy,
        )

    def _book_sell_fill(
        self,
        session: PaperSession,
        bar: HistoricalBar,
        signal: Signal,
        view,
        *,
        price: float,
        base_price: float,
        order_id: str,
        via_oms: bool,
    ) -> None:
        qty = view.quantity
        entry_price = float(view.entry_price)
        commission = self._commission(price * qty, Side.SELL)
        net_pnl = (price - entry_price) * qty - commission
        pnl_pct = ((price / entry_price) - 1) * 100 if entry_price > 0 else 0.0
        self._apply_cash(session, price * qty - commission)
        session.daily_pnl += net_pnl
        session.trades.append(
            PaperTrade(
                symbol=bar.symbol,
                side=Side.BUY,
                entry_price=entry_price,
                exit_price=price,
                quantity=qty,
                entry_time=view.entry_time,
                exit_time=bar.timestamp,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                commission=commission,
                slippage_cost=qty * base_price * (self._config.slippage_pct / 100),
                strategy=view.strategy or signal.strategy,
                reasons=list(signal.reasons) or ["paper_signal"],
            )
        )
        self._record_fill(
            session,
            order_id=order_id,
            symbol=bar.symbol,
            exchange=DEFAULT_EXCHANGE,
            side=Side.SELL,
            quantity=qty,
            price=price,
            timestamp=bar.timestamp,
            trade_tag="close",
        )

    def _build_hooks(self) -> SignalProcessorHooks:
        return SignalProcessorHooks(
            equity_for_sizing=lambda session: session.capital,
            position_view=lambda session, symbol: session._to_paper_position(symbol),
            slippage_pct=lambda session, bar: self._config.slippage_pct,
            size_for_simulated=self._size_for_simulated,
            size_for_oms=self._size_for_oms,
            entry_gate=self._entry_gate,
            oms_slippage_pct=lambda config: self._config.slippage_pct,
            buy_order_meta=lambda signal: (signal.strategy, list(signal.reasons)),
            sell_order_meta=lambda signal, view: (view.strategy, list(signal.reasons)),
            book_buy_fill=self._book_buy_fill,
            book_sell_fill=self._book_sell_fill,
        )

    def process(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: PaperSession,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Process a signal through OMS for backtest-live parity.

        Requires the OMS adapter supplied at construction time.
        ``fill_price`` overrides bar.close (used for NEXT_OPEN fills).
        """
        self._impl.process(signal, bar, session, fill_price=fill_price)
