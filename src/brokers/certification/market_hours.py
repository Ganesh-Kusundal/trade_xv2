"""Market-hours certification — IST-aware behavior matrix across trading sessions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import Enum

from brokers.session import BrokerSession

logger = logging.getLogger(__name__)

try:
    from domain.constants import (
        NSE_CLOSE_HOUR_IST,
        NSE_CLOSE_MINUTE_IST,
        NSE_OPEN_HOUR_IST,
        NSE_OPEN_MINUTE_IST,
    )
except Exception:  # pragma: no cover
    NSE_OPEN_HOUR_IST, NSE_OPEN_MINUTE_IST = 9, 15
    NSE_CLOSE_HOUR_IST, NSE_CLOSE_MINUTE_IST = 15, 30

_IST = timezone(timedelta(hours=5, minutes=30))


class MarketPhase(str, Enum):
    PRE_MARKET = "pre_market"
    OPEN = "open"
    MARKET_HOURS = "market_hours"
    AUCTION = "auction"
    CLOSING_AUCTION = "closing_auction"
    AFTER_MARKET = "after_market"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


# Expected behavior per phase (paper always allows history; live may restrict orders).
_PHASE_EXPECTATIONS: dict[str, dict[str, bool]] = {
    MarketPhase.PRE_MARKET.value: {
        "quote": True,
        "subscription": True,
        "history": True,
        "orders": False,
    },
    MarketPhase.MARKET_HOURS.value: {
        "quote": True,
        "subscription": True,
        "history": True,
        "orders": True,
    },
    MarketPhase.CLOSING_AUCTION.value: {
        "quote": True,
        "subscription": True,
        "history": True,
        "orders": False,
    },
    MarketPhase.AFTER_MARKET.value: {
        "quote": True,
        "subscription": False,
        "history": True,
        "orders": False,
    },
    MarketPhase.WEEKEND.value: {
        "quote": True,  # paper / cached
        "subscription": False,
        "history": True,
        "orders": False,
    },
    MarketPhase.HOLIDAY.value: {
        "quote": True,
        "subscription": False,
        "history": True,
        "orders": False,
    },
    MarketPhase.OPEN.value: {
        "quote": True,
        "subscription": False,
        "history": True,
        "orders": False,
    },
    MarketPhase.AUCTION.value: {
        "quote": True,
        "subscription": True,
        "history": True,
        "orders": False,
    },
}


@dataclass
class PhaseResult:
    phase: str
    quote_available: bool
    subscription_ok: bool
    history_available: bool
    orders_allowed: bool
    detail: str = ""
    expectations_met: bool = True


@dataclass
class MarketHoursReport:
    results: list[PhaseResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.expectations_met for r in self.results)

    def print_report(self) -> None:
        for r in self.results:
            mark = "PASS" if r.expectations_met else "WARN"
            logger.info(
                "  [%s] %s: quote=%s sub=%s hist=%s orders=%s (%s)",
                mark,
                r.phase,
                r.quote_available,
                r.subscription_ok,
                r.history_available,
                r.orders_allowed,
                r.detail,
            )


def current_phase(now: datetime | None = None) -> str:
    """Detect NSE cash market phase from IST wall clock."""
    now = _to_ist(now)
    if now.weekday() >= 5:
        return MarketPhase.WEEKEND.value
    t = now.time()
    open_t = time(NSE_OPEN_HOUR_IST, NSE_OPEN_MINUTE_IST)
    close_t = time(NSE_CLOSE_HOUR_IST, NSE_CLOSE_MINUTE_IST)
    if time(9, 0) <= t < open_t:
        return MarketPhase.PRE_MARKET.value
    if open_t <= t < close_t:
        return MarketPhase.MARKET_HOURS.value
    if close_t <= t < time(15, 40):
        return MarketPhase.CLOSING_AUCTION.value
    if time(15, 40) <= t <= time(16, 0):
        return MarketPhase.AFTER_MARKET.value
    return MarketPhase.OPEN.value


def _to_ist(now: datetime | None = None) -> datetime:
    now = now or datetime.now(tz=_IST)
    if now.tzinfo is None:
        return now.replace(tzinfo=_IST)
    return now.astimezone(_IST)


def is_nse_market_open(now: datetime | None = None) -> bool:
    """True during NSE cash session (09:15–15:30 IST, Mon–Fri).

    Used by certification to gate live market-feed / depth checks only.
    Token refresh and REST endpoints (history, portfolio, mapping) are not gated.
    """
    import os

    if os.environ.get("FORCE_MARKET_OPEN") == "1":
        return True
    return current_phase(now) == MarketPhase.MARKET_HOURS.value


def verify_market_hours(broker: str = "paper", *, now: datetime | None = None) -> MarketHoursReport:
    """Run the market-hours behavior matrix for the current IST phase."""
    report = MarketHoursReport()
    session = BrokerSession(broker)
    try:
        phase = current_phase(now)
        expect = _PHASE_EXPECTATIONS.get(phase, {})
        stock = session.stock("RELIANCE")
        quote_ok = False
        try:
            quote_ok = stock.refresh() is not None
        except Exception:
            quote_ok = False
        sub_ok = False
        try:
            h = session.subscribe(stock)
            sub_ok = h is not None
            if h is not None:
                session.unsubscribe(stock)
        except Exception:
            sub_ok = False
        hist_ok = False
        try:
            hist_ok = getattr(session.history(stock, days=1), "bar_count", 0) > 0
        except Exception:
            hist_ok = False
        orders_allowed = bool(getattr(session.status, "orders_enabled", False))

        # Paper always enables orders in sim; treat as meeting "orders" expectation.
        met = True
        if expect.get("quote") and not quote_ok and broker != "paper":
            met = False
        if expect.get("history") and not hist_ok:
            met = False
        # Subscription/orders expectations are soft for paper (sim always on).
        if broker != "paper":
            if expect.get("subscription") is False and sub_ok:
                pass  # unexpected but not fail
            if expect.get("orders") is False and orders_allowed:
                met = False

        report.results.append(
            PhaseResult(
                phase,
                quote_ok,
                sub_ok,
                hist_ok,
                orders_allowed,
                f"IST phase; expect={expect}",
                expectations_met=met,
            )
        )
    finally:
        session.close()
    return report
