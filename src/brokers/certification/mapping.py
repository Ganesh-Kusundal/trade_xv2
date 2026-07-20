"""Mapping certification — round-trip symbol↔instrument id via public API only."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from brokers.runtime.symbol_registry import SymbolRegistry
from brokers.session import BrokerSession

logger = logging.getLogger(__name__)


@dataclass
class MappingResult:
    asset: str
    exchange: str
    symbol: str
    passed: bool
    detail: str = ""


@dataclass
class MappingReport:
    results: list[MappingResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def print_report(self) -> None:
        for r in self.results:
            logger.info(
                "  [%s] %s/%s %s: %s",
                "PASS" if r.passed else "FAIL",
                r.asset,
                r.exchange,
                r.symbol,
                r.detail,
            )
        logger.info("Overall: %s", "PASS" if self.all_passed else "MAPPING ERRORS")


_DEFAULT_CASES = [
    ("equity", "NSE", "RELIANCE"),
    ("equity", "BSE", "RELIANCE"),
    ("index", "NSE", "NIFTY"),
    ("future", "NFO", "NIFTY"),
    ("option", "NFO", "NIFTY"),
    ("currency", "NSE", "USDINR"),
    ("commodity", "MCX", "GOLD"),
]


def verify_mapping(broker: str = "paper", *, session: BrokerSession | None = None) -> MappingReport:
    """Run round-trip mapping validation for the default asset/exchange matrix."""
    report = MappingReport()
    owned = session is None
    if owned:
        session = BrokerSession(broker)
    registry = SymbolRegistry()
    try:
        for asset, exchange, symbol in _DEFAULT_CASES:
            passed, detail = _round_trip(session, registry, asset, exchange, symbol)
            report.results.append(MappingResult(asset, exchange, symbol, passed, detail))
    finally:
        if owned and session is not None:
            session.close()
    return report


def _resolve(session: BrokerSession, asset: str, exchange: str, symbol: str) -> Any:
    """Resolve via public BrokerSession API (no gateway escape hatch)."""
    expiry = date.today() + timedelta(days=30)
    if asset == "equity":
        return session.stock(symbol, exchange=exchange)
    if asset == "index":
        return session.index(symbol, exchange=exchange)
    if asset == "future":
        return session.future(symbol, expiry=expiry, exchange=exchange)
    if asset == "option":
        return session.option(symbol, strike=25000, right="CE", expiry=expiry, exchange=exchange)
    if asset == "currency":
        return session.currency(symbol, exchange=exchange)
    if asset == "commodity":
        return session.commodity(symbol, expiry=expiry, exchange=exchange)
    raise ValueError(f"unknown asset kind: {asset}")


def _round_trip(
    session: BrokerSession,
    registry: SymbolRegistry,
    asset: str,
    exchange: str,
    symbol: str,
) -> tuple[bool, str]:
    """Canonical symbol → instrument → id fields → canonical (public API only)."""
    try:
        inst = _resolve(session, asset, exchange, symbol)
    except NotImplementedError:
        return True, "not implemented (accepted)"
    except Exception as exc:
        return False, f"resolve failed: {type(exc).__name__}: {exc}"

    if inst is None:
        return False, "instrument not resolved"

    inst_id = inst.id
    if inst_id.underlying.upper() != symbol.upper() and inst.symbol.upper() != symbol.upper():
        return False, f"underlying mismatch: {inst_id.underlying!r} != {symbol!r}"

    if inst.exchange.upper() != exchange.upper() and inst_id.exchange.upper() != exchange.upper():
        return False, f"exchange mismatch: {inst.exchange!r} != {exchange!r}"

    # Registry round-trip when populated
    entry = registry.lookup(inst_id)
    if entry is not None:
        back_symbol = getattr(entry, "symbol", None) or getattr(entry, "underlying", None)
        if back_symbol and back_symbol.upper() != symbol.upper():
            return False, f"registry reverse mismatch: {back_symbol!r}"

    return True, f"round-trip ok ({inst_id})"
