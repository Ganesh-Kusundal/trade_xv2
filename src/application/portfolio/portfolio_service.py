"""Portfolio service for P&L, holdings, and tradebook calculations.

Extracts business logic from API route handlers into testable services.

Typed against the canonical domain value objects (``Position``, ``Trade``,
``Balance``) so the portfolio context never depends on loosely-typed
``Any`` managers. The position/trade sources are expressed as structural
:class:`Protocol` types (``PositionStore`` / ``TradeStore``), which keeps this
module decoupled from the OMS implementation while remaining fully typed.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from domain import Position, Trade

logger = logging.getLogger(__name__)


class PositionStore(Protocol):
    """Structural type for anything that can supply the current positions."""

    def get_positions(self) -> Sequence[Position]:
        """Return the current open/closed positions."""
        ...


class TradeStore(Protocol):
    """Structural type for anything that can supply the tradebook."""

    def get_trades(self, symbol: str | None = None) -> Sequence[Trade]:
        """Return trades, optionally filtered by symbol."""
        ...


@dataclass(frozen=True)
class PositionSummary:
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    pnl_pct: float


@dataclass(frozen=True)
class PortfolioSummary:
    positions: list[PositionSummary]
    count: int
    total_pnl: float
    total_pnl_percent: float


@dataclass(frozen=True)
class HoldingSummary:
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    current_price: float
    invested_value: float
    current_value: float
    pnl: float
    pnl_percent: float


@dataclass(frozen=True)
class HoldingsSummary:
    holdings: list[HoldingSummary]
    count: int
    total_value: float
    total_invested: float
    total_pnl: float


@dataclass(frozen=True)
class TradeSummary:
    trades: list[Trade]
    total_pnl: float
    winning_trades: int
    losing_trades: int
    win_rate: float


class PortfolioService:
    """Service for portfolio calculations and queries.

    Encapsulates P&L, holdings, and tradebook logic that was
    previously in API route handlers.
    """

    def __init__(
        self,
        position_manager: PositionStore,
        order_manager: TradeStore | None = None,
    ) -> None:
        self._positions: PositionStore = position_manager
        self._oms: TradeStore | None = order_manager

    def get_positions(self, status_filter: str | None = None) -> PortfolioSummary:
        """Get positions with P&L calculations.

        Parameters
        ----------
        status_filter : str, optional
            Filter: "open", "closed", or None for all.

        Returns
        -------
        PortfolioSummary
            Positions with calculated P&L.
        """
        positions: Sequence[Position] = self._positions.get_positions()

        if status_filter and status_filter != "all":
            positions = [p for p in positions if (status_filter == "open") == (p.quantity != 0)]

        summaries = []
        total_pnl = Decimal("0")
        total_value = Decimal("0")

        for p in positions:
            unrealized = float(p.unrealized_pnl)
            realized = float(p.realized_pnl)
            pnl = unrealized + realized

            avg_price = float(p.avg_price)
            quantity = abs(p.quantity)
            current_price = float(p.ltp)

            pnl_pct = (
                float((p.unrealized_pnl + p.realized_pnl) / (abs(p.avg_price) * abs(p.quantity)) * 100)
                if p.avg_price and p.quantity
                else 0.0
            )

            summaries.append(PositionSummary(
                symbol=p.symbol,
                exchange=p.exchange,
                quantity=p.quantity,
                average_price=avg_price,
                current_price=current_price,
                unrealized_pnl=unrealized,
                realized_pnl=realized,
                pnl_pct=pnl_pct,
            ))

            total_pnl += Decimal(str(pnl))
            if p.quantity != 0:
                total_value += Decimal(str(quantity * avg_price))

        return PortfolioSummary(
            positions=summaries,
            count=len(summaries),
            total_pnl=float(total_pnl),
            total_pnl_percent=float((total_pnl / total_value * 100) if total_value else 0.0),
        )

    def get_holdings(self) -> HoldingsSummary:
        """Get holdings with cost basis and current value.

        Returns
        -------
        HoldingsSummary
            Holdings with P&L calculations.
        """
        positions: Sequence[Position] = self._positions.get_positions()

        holdings = []
        total_value = 0.0
        total_invested = 0.0
        total_pnl = 0.0

        for p in positions:
            if p.quantity != 0:
                current_price = float(p.ltp)
                avg_price = float(p.avg_price)
                quantity = abs(p.quantity)

                invested = quantity * avg_price
                current = quantity * current_price
                pnl = current - invested

                holdings.append(HoldingSummary(
                    symbol=p.symbol,
                    exchange=p.exchange,
                    quantity=quantity,
                    average_price=avg_price,
                    current_price=current_price,
                    invested_value=invested,
                    current_value=current,
                    pnl=pnl,
                    pnl_percent=(pnl / invested * 100) if invested > 0 else 0.0,
                ))

                total_value += current
                total_invested += invested
                total_pnl += pnl

        return HoldingsSummary(
            holdings=holdings,
            count=len(holdings),
            total_value=total_value,
            total_invested=total_invested,
            total_pnl=total_pnl,
        )

    def get_tradebook(
        self,
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> TradeSummary:
        """Get tradebook with P&L calculations.

        Parameters
        ----------
        symbol : str, optional
            Filter by symbol.
        from_date : str, optional
            Filter trades from this date.
        to_date : str, optional
            Filter trades up to this date.

        Returns
        -------
        TradeSummary
            Trades with P&L summary.
        """
        if self._oms is None:
            return TradeSummary(
                trades=[], total_pnl=0.0,
                winning_trades=0, losing_trades=0, win_rate=0.0,
            )

        trades: Sequence[Trade] = self._oms.get_trades(symbol=symbol)
        total_pnl = sum(float(getattr(t, "pnl", 0) or 0) for t in trades)
        winning = [t for t in trades if getattr(t, "pnl", 0) and float(t.pnl) > 0]
        losing = [t for t in trades if getattr(t, "pnl", 0) and float(t.pnl) < 0]

        return TradeSummary(
            trades=list(trades),
            total_pnl=total_pnl,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / len(trades) if trades else 0.0,
        )
