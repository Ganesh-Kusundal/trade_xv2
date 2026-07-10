"""AgentTools — the AI agent tool surface.

Thin wrappers over the already-real SDK surface (Session, Instrument,
AccountView, RiskProfile) — nothing new underneath. Same contract as any
other Session client: same OrderIntent -> OrderServicePort path, same
risk/idempotency/audit, no exceptions. See
docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART5.md §7.

Deliberately excluded from this surface: no get_raw_broker_client(), no
execute_arbitrary_code(), no direct ExecutionProvider handle. An agent
that needs a capability not on this list needs the capability added to
the SDK first, available to every client — not a special back door added
just for agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from interface.agent.guardrails import AgentGuardrails

if TYPE_CHECKING:
    from domain.universe import Session


@dataclass(frozen=True)
class DryRunResult:
    """Returned by place_order(..., dry_run=True) instead of placing
    anything. Lets an agent (or a human testing one) see what *would*
    happen before committing capital."""

    symbol: str
    exchange: str
    side: str
    quantity: int
    order_type: str
    price: Decimal | None
    risk_headroom_pct: Decimal | None


class AgentTools:
    """The tool surface exposed to an AI agent for one connected Session.

    One instance per agent session, paired with its own AgentGuardrails
    (never share a AgentGuardrails instance across agents — the whole
    point is per-session budget isolation).
    """

    def __init__(self, session: "Session", guardrails: AgentGuardrails | None = None) -> None:
        self._session = session
        self._guardrails = guardrails or AgentGuardrails()

    # ── Read-only tools ────────────────────────────────────────────────

    def get_quote(self, symbol: str, exchange: str = "NSE") -> dict[str, Any]:
        self._guardrails.check_rate_limit("read")
        self._guardrails.check_symbol_allowed(symbol)
        inst = self._session.universe.equity(symbol, exchange)
        inst.refresh()
        return {
            "symbol": symbol,
            "exchange": exchange,
            "ltp": inst.ltp,
            "bid": inst.bid,
            "ask": inst.ask,
            "volume": inst.volume,
        }

    def get_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "5m",
        days: int = 5,
    ) -> Any:
        self._guardrails.check_rate_limit("read")
        self._guardrails.check_symbol_allowed(symbol)
        inst = self._session.universe.equity(symbol, exchange)
        return inst.history(timeframe=timeframe, days=days)

    def get_option_chain(self, symbol: str, expiry: Any = None) -> Any:
        self._guardrails.check_rate_limit("read")
        self._guardrails.check_symbol_allowed(symbol)
        return self._session.option_chain(symbol, expiry=expiry)

    def get_positions(self) -> list[Any]:
        self._guardrails.check_rate_limit("read")
        return list(self._session.account.refresh().positions)

    def get_portfolio(self) -> dict[str, Any]:
        self._guardrails.check_rate_limit("read")
        portfolio = self._session.account.refresh().portfolio
        return {
            "position_count": portfolio.position_count,
            "total_pnl": portfolio.total_pnl,
            "gross_exposure": portfolio.gross_exposure,
        }

    def get_risk_status(self) -> dict[str, Any]:
        """The concrete justification for RiskProfile existing on the SDK
        at all (Part 2 §3.1): an agent asking "how much room do I have"
        before attempting an order."""
        self._guardrails.check_rate_limit("read")
        profile = self._session.account.risk_profile
        if profile is None:
            return {"configured": False}
        return {
            "configured": True,
            "kill_switch": profile.kill_switch,
            "max_daily_loss_pct": profile.max_daily_loss_pct,
            "max_position_pct": profile.max_position_pct,
            "headroom_pct": profile.headroom_pct(),
        }

    # ── Order tools — always via OrderIntent -> OrderServicePort ────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: Decimal | None = None,
        *,
        dry_run: bool = False,
    ) -> Any:
        """Never calls a raw ExecutionProvider — same session.buy/sell
        path (OrderIntent -> OrderServicePort) as every other client.

        dry_run=True returns a DryRunResult describing what would happen
        (including current risk headroom) without calling
        OrderServicePort.place() at all.
        """
        self._guardrails.check_rate_limit("order")
        self._guardrails.check_symbol_allowed(symbol)

        if dry_run:
            profile = self._session.account.risk_profile
            return DryRunResult(
                symbol=symbol,
                exchange=exchange,
                side=side.upper(),
                quantity=quantity,
                order_type=order_type.upper(),
                price=price,
                risk_headroom_pct=profile.headroom_pct() if profile is not None else None,
            )

        inst = self._session.universe.equity(symbol, exchange)
        if side.upper() == "BUY":
            return inst.buy(quantity, price=price, order_type=order_type)
        return inst.sell(quantity, price=price, order_type=order_type)

    def cancel_order(self, order_id: str) -> Any:
        self._guardrails.check_rate_limit("order")
        return self._session.cancel(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> Any:
        self._guardrails.check_rate_limit("order")
        return self._session.modify(order_id, **changes)


__all__ = ["AgentTools", "DryRunResult"]
