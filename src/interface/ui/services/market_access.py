"""Domain-level market data access for UI — no wire gateway .ltp/.quote/.funds."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain.universe import Session as DomainSession

if TYPE_CHECKING:
    from runtime.platform_bridge import broker_session_type as BrokerSession

    SessionLike = DomainSession | BrokerSession
else:
    SessionLike = Any


def _domain_session(session: SessionLike) -> DomainSession:
    if hasattr(session, "stock"):
        return session.session  # BrokerSession
    return session


def refresh_quote(session: SessionLike, symbol: str, exchange: str = "NSE") -> Any:
    """Refresh and return quote for a cash equity symbol."""
    if hasattr(session, "stock"):
        return session.stock(symbol, exchange).refresh()
    return session.universe.equity(symbol, exchange).refresh()


def quote_ltp(session: SessionLike, symbol: str, exchange: str = "NSE") -> Decimal | None:
    """Last traded price via domain instrument refresh."""
    q = refresh_quote(session, symbol, exchange)
    ltp = getattr(q, "ltp", None)
    if ltp is None:
        return None
    return ltp if isinstance(ltp, Decimal) else Decimal(str(ltp))


def fetch_funds(session: SessionLike) -> Any:
    """Account funds via domain session (not wire gateway.funds())."""
    acct = _domain_session(session).account
    if hasattr(acct, "refresh"):
        acct.refresh()
    funds = getattr(acct, "funds", None)
    if callable(funds):
        funds = funds()
    return funds


def refresh_account(session: SessionLike) -> Any:
    """Refresh and return session account view (positions, holdings, funds)."""
    from application.portfolio.active_session import refresh_account as _refresh

    return _refresh(session)


def fetch_history(
    session: SessionLike,
    symbol: str,
    *,
    exchange: str = "NSE",
    timeframe: str = "1D",
    days: int = 30,
) -> Any:
    """Historical series via domain instrument."""
    if hasattr(session, "history"):
        return session.history(
            session.stock(symbol, exchange=exchange), timeframe=timeframe, days=days
        )
    inst = session.universe.equity(symbol, exchange)
    return inst.history(timeframe=timeframe, days=days)


def fetch_depth(session: SessionLike, symbol: str, exchange: str = "NSE") -> Any:
    """Market depth via domain instrument (not wire gateway.depth())."""
    if hasattr(session, "stock"):
        return session.stock(symbol, exchange).depth()
    return session.universe.equity(symbol, exchange).depth()


def fetch_history_df(
    session: SessionLike,
    symbol: str,
    *,
    exchange: str = "NSE",
    timeframe: str = "1D",
    days: int = 30,
) -> Any:
    """Historical OHLCV as a DataFrame via domain instrument."""
    series = fetch_history(session, symbol, exchange=exchange, timeframe=timeframe, days=days)
    if hasattr(series, "to_dataframe"):
        return series.to_dataframe()
    return series
