"""Portfolio services — positions, holdings, funds, and orders."""

from __future__ import annotations

from typing import Any

from brokers.session import BrokerSession

from ._session import _borrow_session


def get_positions(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        acct = s.account
        if hasattr(acct, "refresh"):
            acct.refresh()
        return acct.positions
    finally:
        if close:
            s.close()


def get_holdings(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        acct = s.account
        if hasattr(acct, "refresh"):
            acct.refresh()
        return acct.holdings
    finally:
        if close:
            s.close()


def get_funds(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        acct = s.account
        if hasattr(acct, "refresh"):
            acct.refresh()
        return acct.funds
    finally:
        if close:
            s.close()


def get_orders(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.orders()
    finally:
        if close:
            s.close()


__all__ = [
    "get_positions",
    "get_holdings",
    "get_funds",
    "get_orders",
]
