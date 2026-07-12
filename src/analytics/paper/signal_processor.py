"""Signal processing for paper trading — routes actionable signals through OMS.

Extracted from ``analytics.paper.engine.PaperTradingEngine`` so the engine can
stay a thin facade. The processor depends on the paper ``config``, an OMS
backtest adapter for order routing, and a fill-recording callback supplied by
the engine (it applies fills through the engine's FillReducer / PortfolioProjector).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from analytics.paper.models import PaperSession, PositionMeta, Side
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.trading_costs import apply_slippage as _apply_slippage

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
    """

    def __init__(
        self,
        config,
        oms_adapter: OmsBacktestAdapterPort,
        record_fill,
    ) -> None:
        self._config = config
        self._oms_adapter = oms_adapter
        self._record_fill = record_fill

    def process(self, signal: Signal, bar: HistoricalBar, session: PaperSession) -> None:
        """Process a signal through OMS for backtest-live parity.

        Requires the OMS adapter supplied at construction time.
        """
        if not signal.is_actionable:
            return

        self._process_via_oms(signal, bar, session)

    def _process_via_oms(
        self, signal: Signal, bar: HistoricalBar, session: PaperSession
    ) -> None:
        """Route paper signals through OMS for parity with live/replay."""
        config = self._config
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
            price = _apply_slippage(
                Decimal(str(bar.close)), side="BUY", slippage_pct=config.slippage_pct
            )
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
                cost = float(price) * qty + config.commission_flat
                session.capital -= cost
                self._record_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=qty,
                    price=float(price),
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
            domain_pos = session._domain_position(bar.symbol)
            if domain_pos is None or domain_pos.quantity <= 0:
                return
            qty = domain_pos.quantity
            entry_price = float(domain_pos.avg_price)
            price = _apply_slippage(
                Decimal(str(bar.close)), side="SELL", slippage_pct=config.slippage_pct
            )
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                proceeds = float(price) * qty - config.commission_flat
                session.capital += proceeds
                simple_pnl = (float(price) - entry_price) * qty - config.commission_flat
                session.daily_pnl += simple_pnl
                self._record_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.SELL,
                    quantity=qty,
                    price=float(price),
                    timestamp=bar.timestamp,
                    trade_tag="close",
                )
                session.clear_position(bar.symbol)
