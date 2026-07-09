"""AccountView — session-level portfolio / holdings / funds without gateways.

Built from :class:`~domain.ports.protocols.ExecutionProvider` at composition
root. Strategy code uses ``session.account``, never broker transport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.portfolio.portfolio import Portfolio

if TYPE_CHECKING:
    from domain.entities.account import Balance
    from domain.entities.position import Holding, Position
    from domain.ports.protocols import ExecutionProvider


class AccountView:
    """Live account snapshot surface (positions, holdings, funds, Portfolio)."""

    def __init__(self, execution_provider: "ExecutionProvider | None" = None) -> None:
        self._ep = execution_provider
        self._portfolio = Portfolio()
        self._positions: list[Any] = []
        self._holdings: list[Any] = []
        self._funds: Any | None = None
        self._refreshed = False

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def positions(self) -> list:
        return list(self._positions)

    @property
    def holdings(self) -> list:
        return list(self._holdings)

    @property
    def funds(self) -> Any | None:
        return self._funds

    @property
    def is_refreshed(self) -> bool:
        return self._refreshed

    def refresh(self) -> "AccountView":
        """Pull positions / holdings / funds from ExecutionProvider into domain objects."""
        if self._ep is None:
            raise RuntimeError(
                "AccountView has no ExecutionProvider. "
                "Use tradex.connect(...) which wires execution for paper/live."
            )
        raw_pos = []
        raw_hold = []
        funds = None
        try:
            raw_pos = list(self._ep.get_positions() or [])
        except Exception:
            raw_pos = []
        try:
            raw_hold = list(self._ep.get_holdings() or [])
        except Exception:
            raw_hold = []
        try:
            funds = self._ep.get_funds()
        except Exception:
            funds = None

        self._positions = raw_pos
        self._holdings = raw_hold
        self._funds = funds
        self._portfolio = Portfolio()
        for p in raw_pos:
            norm = self._coerce_position(p)
            if norm is not None:
                self._portfolio.add_position(norm)
        self._refreshed = True
        return self

    @staticmethod
    def _coerce_position(raw: Any) -> "Position | None":
        from decimal import Decimal

        from domain.entities.position import Position

        if isinstance(raw, Position):
            return raw
        if raw is None:
            return None
        symbol = getattr(raw, "symbol", None) or (raw.get("symbol") if isinstance(raw, dict) else None)
        if not symbol:
            return None
        exchange = getattr(raw, "exchange", None) or (
            raw.get("exchange", "NSE") if isinstance(raw, dict) else "NSE"
        )
        qty = getattr(raw, "quantity", None)
        if qty is None and isinstance(raw, dict):
            qty = raw.get("quantity", 0)
        avg = getattr(raw, "avg_price", None)
        if avg is None and isinstance(raw, dict):
            avg = raw.get("avg_price", 0)
        ltp = getattr(raw, "ltp", None)
        if ltp is None and isinstance(raw, dict):
            ltp = raw.get("ltp", 0)
        return Position(
            symbol=str(symbol),
            exchange=str(exchange or "NSE"),
            quantity=int(qty or 0),
            avg_price=Decimal(str(avg or 0)),
            ltp=Decimal(str(ltp or 0)),
        )

    def describe(self) -> dict[str, Any]:
        return {
            "refreshed": self._refreshed,
            "position_count": self._portfolio.position_count,
            "holding_count": len(self._holdings),
            "total_pnl": str(self._portfolio.total_pnl),
            "gross_exposure": str(self._portfolio.gross_exposure),
            "has_funds": self._funds is not None,
        }

    def __repr__(self) -> str:
        return (
            f"AccountView(positions={self._portfolio.position_count}, "
            f"holdings={len(self._holdings)}, refreshed={self._refreshed})"
        )
