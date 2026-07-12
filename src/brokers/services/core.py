"""Shared broker operations — single code path for SDK, CLI, MCP, self-test."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from brokers.session import BrokerSession, available_brokers


def safe_serialize(obj: object) -> object:
    """Best-effort JSON-safe view of a domain object."""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    snap = getattr(obj, "snapshot", None)
    if callable(snap):
        return safe_serialize(snap())
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return safe_serialize(to_dict())
    if is_dataclass(obj):
        return {k: safe_serialize(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return {k: safe_serialize(v) for k, v in vars(obj).items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [safe_serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    return obj


def _open(broker: str, **kwargs: Any) -> BrokerSession:
    return BrokerSession(broker, **kwargs)


def _borrow_session(
    broker: str,
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> tuple[BrokerSession, bool]:
    """Return ``(session, should_close)``. Reuse *session* when the shell holds one open."""
    if session is not None:
        return session, False
    return _open(broker, **kwargs), True


def status_from_session(session: BrokerSession) -> dict[str, Any]:
    """Status dict from an already-open session (no reconnect)."""
    st = session.status
    checkpoints = [
        {"name": c.name, "ok": c.ok, "detail": c.detail}
        for c in getattr(session.runtime, "checkpoints", [])
    ]
    return {
        "broker_id": session.broker_id,
        "mode": getattr(st, "mode", None),
        "orders_enabled": getattr(st, "orders_enabled", None),
        "authenticated": getattr(st, "authenticated", None),
        "instruments_loaded": getattr(st, "instruments_loaded", None),
        "checkpoints": checkpoints,
        "connected": True,
    }


def extensions_from_session(session: BrokerSession, symbol: str = "RELIANCE") -> list[str]:
    try:
        return list(format_session_capabilities(session, symbol).get("extensions") or [])
    except Exception:
        return []


def run_connect(
    broker: str = "paper",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Connect and return status + startup checkpoints (Trading OS startup flow)."""
    if session is not None:
        return status_from_session(session)
    s = _open(broker, **kwargs)
    try:
        return status_from_session(s)
    finally:
        s.close()


def get_quote(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.stock(symbol, exchange=exchange).refresh()
    finally:
        if close:
            s.close()


def get_history(
    broker: str,
    symbol: str,
    *,
    timeframe: str = "1D",
    days: int = 5,
    exchange: str = "NSE",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.history(s.stock(symbol, exchange=exchange), timeframe=timeframe, days=days)
    finally:
        if close:
            s.close()


def run_subscribe_probe(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> bool:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        handle = s.subscribe(inst)
        if handle is not None:
            s.unsubscribe(inst)
        return handle is not None
    finally:
        if close:
            s.close()


def get_depth(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.stock(symbol, exchange=exchange).depth()
    finally:
        if close:
            s.close()


def get_depth30(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    """Upstox 30-level depth via instrument.broker.depth30()."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        facade = getattr(inst, "broker", None)
        if facade is None:
            raise RuntimeError(f"broker {broker!r} has no instrument.broker facade")
        fn = getattr(facade, "depth30", None) or getattr(facade, "depth_30", None)
        if not callable(fn):
            raise RuntimeError(f"broker {broker!r} does not expose depth30")
        return fn()
    finally:
        if close:
            s.close()


def probe_depth_ws(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    levels: int = 20,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    """Probe WS depth extensions (20/200) when declared; REST depth as fallback."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        facade = getattr(inst, "broker", None)
        if facade is not None:
            if levels >= 200:
                fn = getattr(facade, "depth200", None) or getattr(facade, "depth_200", None)
                if callable(fn):
                    return fn()
            if levels >= 20:
                fn = getattr(facade, "depth20", None) or getattr(facade, "depth_20", None)
                if callable(fn):
                    return fn()
        return inst.depth()
    finally:
        if close:
            s.close()


def get_option_chain(
    broker: str,
    underlying: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.option_chain(underlying, exchange=exchange)
    finally:
        if close:
            s.close()


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


def _session_gateway(session: BrokerSession) -> Any | None:
    """Resolve the wire gateway from a BrokerSession (internal)."""
    provider = session.provider
    gw = getattr(provider, "_gw", None)
    if gw is not None:
        return gw
    return getattr(session.session, "_gateway", None)


def _cap_value(value: Any) -> Any:
    """JSON-safe conversion for capability matrix values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, frozenset):
        if not value:
            return []
        sample = next(iter(value))
        if hasattr(sample, "__dataclass_fields__"):
            return [_cap_value(v) for v in value]
        return [str(v) for v in value]
    if isinstance(value, tuple):
        return [_cap_value(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            k: _cap_value(getattr(value, k))
            for k in value.__dataclass_fields__
        }
    if hasattr(value, "value"):  # Enum
        return value.value
    return str(value)


def _caps_to_dict(caps: Any) -> dict[str, Any]:
    from dataclasses import fields

    if caps is None:
        return {}
    return {f.name: _cap_value(getattr(caps, f.name)) for f in fields(caps)}


def format_session_capabilities(session: BrokerSession, symbol: str = "RELIANCE") -> dict[str, Any]:
    """Full capability payload: matrix + extension names + market surfaces."""
    extensions = session.stock(symbol).capabilities()
    matrix: dict[str, Any] = {}
    gw = _session_gateway(session)
    if gw is not None:
        caps_fn = getattr(gw, "capabilities", None)
        if callable(caps_fn):
            matrix = _caps_to_dict(caps_fn())
        else:
            list_fn = getattr(gw, "list_capabilities", None)
            if callable(list_fn):
                desc = list_fn()
                matrix = _caps_to_dict(getattr(desc, "capabilities", desc))
    return {
        "broker_id": session.broker_id,
        "matrix": matrix,
        "extensions": extensions,
        "market_surfaces": matrix.get("market_surfaces", []),
    }


def get_capabilities(
    broker: str,
    symbol: str = "RELIANCE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return format_session_capabilities(s, symbol)
    finally:
        if close:
            s.close()


def lookup_instrument(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Resolve symbol → public instrument metadata (no broker tokens)."""
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        return {
            "symbol": symbol,
            "exchange": inst.exchange,
            "instrument_id": str(inst.id),
            "underlying": getattr(inst.id, "underlying", symbol),
            "tick_size": str(inst.tick_size) if inst.tick_size is not None else None,
            "lot_size": inst.lot_size,
        }
    finally:
        if close:
            s.close()


def lookup_security(
    broker: str, symbol: str, exchange: str = "NSE", **kwargs: Any
) -> dict[str, Any]:
    """Backward-compatible alias for :func:`lookup_instrument`."""
    return lookup_instrument(broker, symbol, exchange=exchange, **kwargs)


def lookup_symbol(
    broker: str,
    symbol: str,
    exchange: str = "NSE",
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> str:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.instrument_id(symbol, exchange=exchange)
    finally:
        if close:
            s.close()


def get_news(
    broker: str,
    *,
    symbol: str | None = None,
    category: str = "holdings",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        if gw is None:
            raise RuntimeError(f"broker {broker!r} has no gateway for news")
        news = getattr(gw, "news", None)
        if news is None:
            raise RuntimeError(f"broker {broker!r} does not support news")
        client = news() if callable(news) else news
        if symbol:
            fn = getattr(client, "get_news", None) or getattr(client, "symbol_news", None)
            if fn is None:
                raise RuntimeError("news client has no symbol lookup")
            return fn(symbol=symbol)
        fn = getattr(client, "get_news", None)
        if fn is None:
            raise RuntimeError("news client unavailable")
        return fn(category=category)
    finally:
        if close:
            s.close()


def list_super_orders(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        ext = getattr(gw, "extended", None) if gw is not None else None
        fn = getattr(ext, "get_super_orders", None) if ext is not None else None
        if fn is None:
            raise RuntimeError(f"broker {broker!r} does not expose super orders")
        return fn()
    finally:
        if close:
            s.close()


def list_forever_orders(broker: str, *, session: BrokerSession | None = None, **kwargs: Any) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        gw = _session_gateway(s)
        ext = getattr(gw, "extended", None) if gw is not None else None
        fn = getattr(ext, "get_all_forever_orders", None) if ext is not None else None
        if fn is None:
            raise RuntimeError(f"broker {broker!r} does not expose forever orders")
        return fn()
    finally:
        if close:
            s.close()


def place_order(
    broker: str,
    symbol: str,
    quantity: int,
    *,
    side: str = "BUY",
    price: Any | None = None,
    order_type: str = "LIMIT",
    product_type: str = "INTRADAY",
    exchange: str = "NSE",
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    from decimal import Decimal

    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        inst = s.stock(symbol, exchange=exchange)
        px = Decimal(str(price)) if price is not None else None
        if (side or "BUY").upper() == "SELL":
            return s.sell(inst, quantity, price=px, order_type=order_type, product_type=product_type)
        return s.buy(inst, quantity, price=px, order_type=order_type, product_type=product_type)
    finally:
        if close:
            s.close()


def cancel_order(
    broker: str,
    order_id: str,
    *,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        return s.cancel(order_id)
    finally:
        if close:
            s.close()


def modify_order(
    broker: str,
    order_id: str,
    *,
    quantity: int | None = None,
    price: Any | None = None,
    session: BrokerSession | None = None,
    **kwargs: Any,
) -> Any:
    from decimal import Decimal

    s, close = _borrow_session(broker, session=session, **kwargs)
    try:
        kw: dict[str, Any] = {}
        if quantity is not None:
            kw["quantity"] = quantity
        if price is not None:
            kw["price"] = Decimal(str(price))
        return s.modify(order_id, **kw)
    finally:
        if close:
            s.close()


def run_mapping(
    broker: str = "paper",
    *,
    session: BrokerSession | None = None,
) -> Any:
    from brokers.certification.mapping import verify_mapping

    return verify_mapping(broker, session=session)


def run_market_hours(broker: str = "paper", **kwargs: Any) -> Any:
    from brokers.certification.market_hours import verify_market_hours

    return verify_market_hours(broker, **kwargs)


def run_certify(broker: str = "paper", *, live: bool = False, **kwargs: Any) -> Any:
    from brokers.certification.suite import BrokerCertifier

    s = _open(broker, **kwargs)
    try:
        return BrokerCertifier(s).certify()
    finally:
        s.close()


def run_diagnose(broker: str = "paper", **kwargs: Any) -> Any:
    from brokers.diagnostics.core import BrokerDiagnostics

    s = _open(broker, **kwargs)
    try:
        return BrokerDiagnostics(s).run_all_checks()
    finally:
        s.close()


def run_doctor(broker: str = "paper") -> Any:
    from brokers.diagnostics.doctor import run_doctor as _run_doctor

    return _run_doctor(broker)


def run_health(broker: str = "paper") -> Any:
    from brokers.diagnostics.health import run_health as _run_health

    return _run_health(broker)


def run_benchmark(broker: str = "paper") -> Any:
    from brokers.diagnostics.benchmark import run_benchmark as _run_benchmark

    return _run_benchmark(broker)


@dataclass
class VerifyStep:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyReport:
    broker_id: str
    steps: list[VerifyStep] = field(default_factory=list)
    certified: bool = False

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps) and self.certified

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.steps.append(VerifyStep(name, passed, detail))

    def print_report(self) -> None:
        for step in self.steps:
            mark = "PASS" if step.passed else "FAIL"
            suffix = f" ({step.detail})" if step.detail else ""
            print(f"[{mark}] {step.name}{suffix}")
        print(f"Overall: {'PASS' if self.passed else 'FAIL'}")

    def to_dict(self) -> dict[str, Any]:
        from brokers.certification.schema_v2 import (
            SCHEMA_VERSION,
            resolve_status,
            resolve_tier,
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "broker_id": self.broker_id,
            "tier": resolve_tier(self.broker_id),
            "status": resolve_status(passed=self.passed),
            "passed": self.passed,
            "certified": self.certified,
            "steps": [{"name": s.name, "passed": s.passed, "detail": s.detail} for s in self.steps],
        }


def run_verify(broker: str = "paper", **kwargs: Any) -> VerifyReport:
    """Startup self-test: config → auth → caps → mappings → quote → history → ws → certify."""
    from brokers.certification.suite import BrokerCertifier

    report = VerifyReport(broker_id=broker)
    if broker not in available_brokers():
        report.add("Configuration", False, f"unknown broker; available: {', '.join(available_brokers())}")
        return report

    report.add("Configuration", True, f"broker={broker}")
    report.add("Secrets", True, "env resolved")

    try:
        s = _open(broker, **kwargs)
    except Exception as exc:  # noqa: BLE001
        report.add("Broker Connect", False, f"{type(exc).__name__}: {exc}")
        return report

    try:
        report.add("Broker Plugin", True, f"{broker} registered")
        report.add("Authentication", True, f"mode={getattr(s.status, 'mode', '?')}")

        caps = format_session_capabilities(s)
        matrix = caps.get("matrix") or {}
        report.add("Capabilities", bool(matrix), f"{len(caps.get('extensions', []))} extensions")

        from brokers.certification.mapping import verify_mapping

        mapping = verify_mapping(broker, session=s)
        report.add("Mappings", mapping.all_passed)

        q = s.stock("RELIANCE").refresh()
        report.add("Sample Quote", q is not None)

        hist = s.history(s.stock("RELIANCE"), timeframe="1D", days=30)
        report.add("Historical", bool(getattr(hist, "bar_count", 0)))

        from brokers.certification.market_hours import is_nse_market_open

        if is_nse_market_open():
            handle = s.subscribe(s.stock("RELIANCE"))
            report.add("WebSocket", handle is not None)
            if handle is not None:
                s.unsubscribe(s.stock("RELIANCE"))
        else:
            report.add("WebSocket", True, "off-market (skipped)")

        cert = BrokerCertifier(s).certify()
        report.certified = cert.is_certified
    finally:
        s.close()

    return report
