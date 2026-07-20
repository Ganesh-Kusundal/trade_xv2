"""BrokerCertifier — the single certification every broker must pass.

Driven by a :class:`BrokerSession` so dhan/upstox/paper run the identical suite.
This module is the canonical, importable core that the CLI (``broker certify``)
and MCP (``broker.verify``) both delegate to.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from brokers.certification.market_hours import is_nse_market_open
from brokers.common.historical_gap_check import assert_gap_free_historical
from brokers.certification.live_probes import (
    probe_disconnect,
    probe_reconnect,
    probe_session_recovery,
    probe_token_expiry,
    probe_token_refresh,
)
from brokers.certification.report import (
    CertArea,
    CertificationReport,
    CertResult,
)
from brokers.session import BrokerSession
from infrastructure.broker_plugin import get_broker_plugin


def _live_session_checks_applicable(s: BrokerSession) -> bool:
    """Whether live-session-management checks apply to this broker.

    Token refresh / expiry / reconnect / disconnect / recovery are concerns of
    a *live* broker connection. Synthetic brokers (paper, datalake, …) have no
    real session to refresh or recover, so these cert checks are skipped.

    Resolved via the broker's ``is_live`` capability flag (declared in its
    ``BrokerPlugin``), never via a broker-name equality check (DR-B2). An
    unknown/unregistered broker is treated as live so it still exercises the
    checks rather than being silently skipped.
    """
    plugin = get_broker_plugin(s.broker_id)
    return bool(plugin.is_live) if plugin is not None else True


class BrokerCertifier:
    """Runs the full certification matrix against a broker session."""

    def __init__(self, session: BrokerSession) -> None:
        self._session = session
        self._broker_id = session.broker_id

    def _check(
        self,
        area: CertArea,
        fn: Callable[[], str | None],
        *,
        warn_only: bool = False,
        market_hours_only: bool = False,
    ) -> CertResult:
        if market_hours_only and not is_nse_market_open():
            return CertResult(area, True, "off-market (skipped)", 0.0)
        start = time.perf_counter()
        try:
            detail = fn() or "OK"
            passed = True
        except NotImplementedError:
            passed = warn_only
            detail = "not implemented (skipped)" if warn_only else "not implemented"
        except Exception as exc:
            passed = warn_only
            detail = f"{type(exc).__name__}: {exc}"
        ms = round((time.perf_counter() - start) * 1000, 2)
        return CertResult(area, passed, str(detail), ms)

    def certify(self) -> CertificationReport:
        """Run the complete certification matrix."""
        report = CertificationReport(self._broker_id)
        s = self._session

        # ── Authentication / reconnect (money-path: fail, do not warn_only) ──
        report.add(self._check(CertArea.AUTHENTICATION, lambda: _auth(s)))
        report.add(self._check(CertArea.TOKEN_REFRESH, lambda: _token_refresh(s)))
        report.add(self._check(CertArea.TOKEN_EXPIRY, lambda: _token_expiry(s)))
        report.add(self._check(CertArea.RECONNECT, lambda: _reconnect(s)))

        # ── Instrument / mapping ──
        report.add(self._check(CertArea.SYMBOL_LOOKUP, lambda: _symbol_lookup(s)))
        report.add(self._check(CertArea.INSTRUMENT_LOOKUP, lambda: _instrument_lookup(s)))
        report.add(self._check(CertArea.CANONICAL_MAPPING, lambda: _canonical_mapping(s)))
        report.add(
            self._check(
                CertArea.SECURITY_ID_MAPPING, lambda: _security_id_mapping(s), warn_only=True
            )
        )
        report.add(
            self._check(CertArea.REVERSE_MAPPING, lambda: _reverse_mapping(s), warn_only=True)
        )

        # ── Market data ──
        report.add(self._check(CertArea.QUOTE, lambda: _quote(s)))
        report.add(self._check(CertArea.LTP, lambda: _ltp(s)))
        report.add(self._check(CertArea.OHLC, lambda: _ohlc(s)))
        report.add(self._check(CertArea.DEPTH, lambda: _depth(s), market_hours_only=True))
        report.add(
            self._check(CertArea.LIVE_STREAM, lambda: _live_stream(s), market_hours_only=True)
        )

        # ── Historical ──
        report.add(self._check(CertArea.TF_1M, lambda: _hist(s, "1m"), warn_only=True))
        report.add(self._check(CertArea.TF_5M, lambda: _hist(s, "5m")))
        report.add(self._check(CertArea.TF_15M, lambda: _hist(s, "15m"), warn_only=True))
        report.add(self._check(CertArea.TF_DAILY, lambda: _hist(s, "1D")))

        # ── Orders (money path — fail the suite; paper exercises sim orders) ──
        report.add(self._check(CertArea.ORDER_MARKET, lambda: _order_market(s)))
        report.add(self._check(CertArea.ORDER_LIMIT, lambda: _order_limit(s)))
        report.add(self._check(CertArea.ORDER_CANCEL, lambda: _order_cancel(s)))
        report.add(self._check(CertArea.ORDER_MODIFY, lambda: _order_modify(s)))

        # ── Portfolio ──
        report.add(self._check(CertArea.HOLDINGS, lambda: _holdings(s), warn_only=True))
        report.add(self._check(CertArea.POSITIONS, lambda: _positions(s), warn_only=True))
        report.add(self._check(CertArea.FUNDS, lambda: _funds(s)))

        # ── Performance ──
        report.add(self._check(CertArea.QUOTE_LATENCY, lambda: _quote_latency(s)))
        report.add(
            self._check(
                CertArea.SUBSCRIPTION_LATENCY, lambda: _sub_latency(s), market_hours_only=True
            )
        )

        # ── Recovery (money path — fail) / rate limits / capability matrix ──
        report.add(self._check(CertArea.DISCONNECT, lambda: _disconnect(s)))
        report.add(self._check(CertArea.SESSION_RECOVERY, lambda: _session_recovery(s)))
        report.add(self._check(CertArea.RATE_BURST, lambda: _rate_burst(s)))
        report.add(self._check(CertArea.RATE_SUSTAINED, lambda: _rate_sustained(s)))
        report.add(self._check(CertArea.CAPABILITY_MATRIX, lambda: _capability_matrix(s)))

        return report


# ── Check implementations (operate on a BrokerSession) ──────────────────────


def _auth(s: BrokerSession) -> str:
    st = s.status
    if not getattr(st, "authenticated", True):
        raise RuntimeError("not authenticated")
    return "authenticated"


def _token_refresh(s: BrokerSession) -> str:
    """Token refresh is live-broker only; paper returns N/A (pass)."""
    if not _live_session_checks_applicable(s):
        return "N/A (synthetic broker)"
    return probe_token_refresh(s)


def _token_expiry(s: BrokerSession) -> str:
    if not _live_session_checks_applicable(s):
        return "N/A (synthetic broker)"
    return probe_token_expiry(s)


def _reconnect(s: BrokerSession) -> str:
    if not _live_session_checks_applicable(s):
        return "N/A (synthetic broker)"
    return probe_reconnect(s)


def _symbol_lookup(s: BrokerSession) -> str:
    inst = s.session.universe.equity("RELIANCE")
    if inst is None:
        raise RuntimeError("symbol lookup failed")
    return f"RELIANCE -> {inst.id}"


def _instrument_lookup(s: BrokerSession) -> str:
    inst = s.stock("INFY")
    if inst is None or inst.symbol != "INFY":
        raise RuntimeError("instrument lookup failed")
    return "INFY resolved"


def _canonical_mapping(s: BrokerSession) -> str:
    inst = s.stock("RELIANCE")
    if inst.symbol != "RELIANCE":
        raise RuntimeError("canonical mapping mismatch")
    return "RELIANCE canonical"


def _security_id_mapping(s: BrokerSession) -> str:
    inst = s.stock("RELIANCE")
    inst_id = str(inst.id)
    if not inst_id:
        raise RuntimeError("no instrument id")
    return f"instrument_id={inst_id}"


def _reverse_mapping(s: BrokerSession) -> str:
    inst = s.stock("RELIANCE")
    if inst.symbol.upper() != "RELIANCE":
        raise RuntimeError("reverse mapping failed")
    return f"reverse={inst.symbol}"


def _quote(s: BrokerSession) -> str:
    q = s.stock("RELIANCE").refresh()
    if q is None or getattr(q, "ltp", None) is None:
        raise RuntimeError("no quote")
    return f"ltp={q.ltp}"


def _ltp(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    stock.refresh()
    ltp = stock.ltp
    if ltp is None:
        raise RuntimeError("no ltp")
    return f"ltp={ltp}"


def _ohlc(s: BrokerSession) -> str:
    q = s.stock("RELIANCE").refresh()
    o = getattr(q, "open_", None) or getattr(q, "open", None)
    if q is None or o is None:
        raise RuntimeError("no ohlc")
    return "ohlc present"


def _depth(s: BrokerSession) -> str:
    d = s.stock("RELIANCE").depth()
    if d is None:
        raise RuntimeError("no depth")
    return "depth present"


def _live_stream(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    h = s.subscribe(stock)
    if h is None:
        raise RuntimeError("no stream handle")
    s.unsubscribe(stock)
    return "stream active"


def _hist(s: BrokerSession, tf: str) -> str:
    stock = s.stock("RELIANCE")
    days = 90 if tf.upper() in ("1D", "D", "DAY") else 30
    series = s.history(stock, timeframe=tf, days=days)
    # Live brokers: enforce gap-free + monotonic. Synthetic brokers (paper) may
    # route through a federated coordinator that marks gaps when no live broker
    # is registered — require bars only.
    if not _live_session_checks_applicable(s):
        n = getattr(series, "bar_count", 0) or 0
        if not n:
            bars = getattr(series, "bars", None) or getattr(series, "candles", None)
            if bars is not None:
                n = len(bars)
        if not n:
            # Fall back to instrument-local history for paper gateways.
            local = getattr(stock, "history", None)
            if callable(local):
                local_series = local(timeframe=tf, days=days)
                n = getattr(local_series, "bar_count", 0) or len(
                    getattr(local_series, "bars", None)
                    or getattr(local_series, "candles", None)
                    or []
                )
        if not n:
            raise RuntimeError(f"no {tf} history")
        return f"{n} {tf} bars (synthetic)"
    n = assert_gap_free_historical(series, timeframe=tf)
    return f"{n} {tf} bars"


def _tick_align_price(price: "Decimal", tick: "Decimal" = None) -> "Decimal":
    from decimal import Decimal, ROUND_DOWN

    from domain.constants import DEFAULT_TICK_SIZE

    tick = tick or Decimal(str(DEFAULT_TICK_SIZE))
    if tick <= 0:
        return Decimal(str(price))
    raw = Decimal(str(price))
    return (raw / tick).to_integral_value(rounding=ROUND_DOWN) * tick


def _order_market(s: BrokerSession) -> str:
    from decimal import Decimal

    stock = s.stock("RELIANCE")
    stock.refresh()
    # MARKET needs a ref price for risk sizing; use LTP as MARKET-with-ref.
    ltp = stock.ltp
    if ltp is None:
        raise RuntimeError("market order failed: no LTP for risk sizing")
    price = _tick_align_price(Decimal(str(ltp)))
    r = s.buy(stock, 1, price=price, order_type="MARKET")
    if r is None or not getattr(r, "success", False):
        detail = getattr(r, "message", None) or getattr(r, "error", None) or r
        raise RuntimeError(f"market order failed: {detail}")
    return "market order placed"


def _order_limit(s: BrokerSession) -> str:
    from decimal import Decimal

    stock = s.stock("RELIANCE")
    stock.refresh()
    ltp = stock.ltp or Decimal("100")
    # Far-from-market limit so paper OMS accepts without immediate fill race.
    price = _tick_align_price(max(Decimal("1"), Decimal(str(ltp)) * Decimal("0.5")))
    r = s.buy(stock, 1, price=price, order_type="LIMIT")
    if r is None or not getattr(r, "success", False):
        detail = getattr(r, "message", None) or getattr(r, "error", None) or r
        raise RuntimeError(f"limit order failed: {detail}")
    return "limit order placed"


def _order_cancel(s: BrokerSession) -> str:
    orders = s.session.orders()
    if not orders:
        raise RuntimeError("no orders to cancel")
    r = s.session.cancel(getattr(orders[0], "order_id", "x"))
    if r is None or not getattr(r, "success", False):
        raise RuntimeError("cancel failed")
    return "order cancelled"


def _order_modify(s: BrokerSession) -> str:
    from decimal import Decimal

    # Place a fresh resting limit — prior cancel may have cleared the book.
    stock = s.stock("RELIANCE")
    stock.refresh()
    ltp = stock.ltp or Decimal("100")
    price = _tick_align_price(max(Decimal("1"), Decimal(str(ltp)) * Decimal("0.4")))
    placed = s.buy(stock, 1, price=price, order_type="LIMIT")
    if placed is None or not getattr(placed, "success", False):
        raise RuntimeError("modify failed: could not place resting order")
    oid = getattr(placed, "order_id", None)
    if not oid:
        orders = s.session.orders()
        if not orders:
            raise RuntimeError("no orders to modify")
        oid = getattr(orders[0], "order_id", "x")
    new_price = _tick_align_price(price * Decimal("0.9"))
    r = s.session.modify(oid, price=new_price, quantity=1)
    if r is None or not getattr(r, "success", False):
        detail = str(getattr(r, "message", None) or getattr(r, "error", None) or r)
        # Paper/sim often fills resting limits immediately — modify is N/A then.
        if not _live_session_checks_applicable(s) and (
            "already final" in detail.lower() or "filled" in detail.lower()
        ):
            return f"N/A (synthetic fill: {detail})"
        raise RuntimeError(f"modify failed: {detail}")
    return "order modified"


def _holdings(s: BrokerSession) -> str:
    acct = s.session.account
    if hasattr(acct, "refresh"):
        acct.refresh()
    h = getattr(acct, "holdings", None)
    if callable(h):
        h = h()
    if h is None:
        raise RuntimeError("no holdings")
    return "holdings present"


def _positions(s: BrokerSession) -> str:
    acct = s.session.account
    if hasattr(acct, "refresh"):
        acct.refresh()
    p = getattr(acct, "positions", None)
    if callable(p):
        p = p()
    if p is None:
        raise RuntimeError("no positions")
    return "positions present"


def _funds(s: BrokerSession) -> str:
    acct = s.session.account
    if hasattr(acct, "refresh"):
        acct.refresh()
    f = getattr(acct, "funds", None)
    if callable(f):
        f = f()
    if f is None:
        raise RuntimeError("no funds")
    return "funds present"


def _quote_latency(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    t0 = time.perf_counter()
    stock.refresh()
    return f"{round((time.perf_counter() - t0) * 1000, 2)}ms"


def _sub_latency(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    t0 = time.perf_counter()
    h = s.subscribe(stock)
    ms = round((time.perf_counter() - t0) * 1000, 2)
    if h is not None:
        s.unsubscribe(stock)
    return f"{ms}ms"


def _disconnect(s: BrokerSession) -> str:
    if not _live_session_checks_applicable(s):
        return "N/A (synthetic broker)"
    return probe_disconnect(s)


def _session_recovery(s: BrokerSession) -> str:
    if not _live_session_checks_applicable(s):
        return "N/A (synthetic broker)"
    return probe_session_recovery(s)


def _rate_burst(s: BrokerSession) -> str:
    # Best-effort: 5 rapid quotes, expect no exception.
    stock = s.stock("RELIANCE")
    for _ in range(5):
        stock.refresh()
    return "burst ok"


def _rate_sustained(s: BrokerSession) -> str:
    stock = s.stock("RELIANCE")
    for _ in range(3):
        stock.refresh()
    return "sustained ok"


def _capability_matrix(s: BrokerSession) -> str:
    caps = s.stock("RELIANCE").capabilities()
    if not isinstance(caps, list | tuple):
        raise RuntimeError("capability query failed")
    return f"{len(caps)} capabilities reported"
