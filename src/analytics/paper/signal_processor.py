"""Signal processing for paper trading — routes actionable signals through OMS.

Extracted from ``analytics.paper.engine.PaperTradingEngine`` so the engine can
stay a thin facade. Slippage is applied **once** inside ``OmsBacktestAdapter``
(same as replay) — this module passes the un-slipped base price.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.paper.models import OrderSide, PaperSession, PaperTrade, Side
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.simulation_position_meta import PositionMeta
from domain.trading_costs import compute_commission

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
        oms_adapter: OmsBacktestAdapterPort,
        record_fill,
        on_cash: Callable[[PaperSession, float], None] | None = None,
    ) -> None:
        self._config = config
        self._oms_adapter = oms_adapter
        self._record_fill = record_fill
        self._on_cash = on_cash

    def _apply_cash(self, session: PaperSession, delta: float) -> None:
        if self._on_cash is not None:
            self._on_cash(session, delta)
        else:
            session.capital += delta

    def _commission(self, notional: float, side: str) -> float:
        cfg = self._config
        return compute_commission(
            notional,
            side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
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
        if not signal.is_actionable:
            return

        self._process_via_oms(signal, bar, session, fill_price=fill_price)

    def _process_via_oms(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: PaperSession,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Route paper signals through OMS for parity with live/replay."""
        config = self._config
        base = float(fill_price if fill_price is not None else bar.close)

        if signal.is_buy and not session.has_position(bar.symbol):
            if session.position_count >= config.max_positions:
                return
            # REF-4: float → Decimal daily-loss gate (domain policy helper).
            if config.max_daily_loss_pct > 0:
                from domain.risk.policy import check_paper_daily_loss

                loss_check = check_paper_daily_loss(
                    session.daily_pnl,
                    session.total_equity,
                    config.max_daily_loss_pct,
                )
                if not loss_check.approved:
                    logger.info(
                        "paper_daily_loss_blocked",
                        extra={"reason": loss_check.reason, "symbol": bar.symbol},
                    )
                    return
            # Un-slipped base — OmsBacktestAdapter applies slippage once (F2a).
            price = Decimal(str(base))
            qty = compute_order_quantity(
                equity=session.capital,
                price=float(price),
                max_position_pct=config.max_position_pct,
            )
            if qty <= 0:
                return
            order_id = self._oms_adapter.open_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                fill_px = resolve_oms_fill_price(
                    self._oms_adapter,
                    order_id,
                    base_price=price,
                    side="BUY",
                    slippage_pct=config.slippage_pct,
                )
                commission = self._commission(fill_px * qty, "BUY")
                self._apply_cash(session, -(fill_px * qty + commission))
                self._record_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=qty,
                    price=fill_px,
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
        elif signal.is_sell and session.has_position(bar.symbol):
            view = session._to_paper_position(bar.symbol)
            if view is None or view.quantity <= 0:
                return
            qty = view.quantity
            entry_price = float(view.entry_price)
            price = Decimal(str(base))
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=view.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                fill_px = resolve_oms_fill_price(
                    self._oms_adapter,
                    order_id,
                    base_price=price,
                    side="SELL",
                    slippage_pct=config.slippage_pct,
                )
                commission = self._commission(fill_px * qty, "SELL")
                net_pnl = (fill_px - entry_price) * qty - commission
                pnl_pct = (
                    ((fill_px / entry_price) - 1) * 100 if entry_price > 0 else 0.0
                )
                slippage_cost = qty * float(price) * (config.slippage_pct / 100)
                self._apply_cash(session, fill_px * qty - commission)
                session.daily_pnl += net_pnl
                session.trades.append(
                    PaperTrade(
                        symbol=bar.symbol,
                        side=OrderSide.BUY,
                        entry_price=entry_price,
                        exit_price=fill_px,
                        quantity=qty,
                        entry_time=view.entry_time,
                        exit_time=bar.timestamp,
                        pnl=net_pnl,
                        pnl_pct=pnl_pct,
                        commission=commission,
                        slippage_cost=slippage_cost,
                        strategy=view.strategy or signal.strategy,
                        reasons=list(signal.reasons) or ["paper_signal"],
                    )
                )
                self._record_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.SELL,
                    quantity=qty,
                    price=fill_px,
                    timestamp=bar.timestamp,
                    trade_tag="close",
                )
                session.clear_position(bar.symbol)
