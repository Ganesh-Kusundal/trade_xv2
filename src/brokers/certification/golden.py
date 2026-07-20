"""Golden dataset certification — validate against known reference data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brokers.session import BrokerSession

logger = logging.getLogger(__name__)

_DATASET_PATH = Path(__file__).with_name("golden_dataset.json")


@dataclass
class GoldenCase:
    symbol: str
    exchange: str
    expected_exchange: str
    expected_tick_size: str | None = None
    expected_lot_size: int | None = None
    expected_security_id: str | None = None
    expected_instrument_id: str | None = None
    asset: str = "equity"


@dataclass
class GoldenResult:
    symbol: str
    passed: bool
    detail: str = ""


@dataclass
class GoldenReport:
    results: list[GoldenResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def print_report(self) -> None:
        for r in self.results:
            logger.info("  [%s] %s: %s", "PASS" if r.passed else "FAIL", r.symbol, r.detail)
        logger.info("Overall: %s", "PASS" if self.all_passed else "GOLDEN MISMATCH")


def load_golden_cases() -> list[GoldenCase]:
    """Load golden reference cases from the versioned JSON dataset."""
    if not _DATASET_PATH.is_file():
        return [
            GoldenCase("RELIANCE", "NSE", "NSE", expected_tick_size="0.05"),
        ]
    data = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    return [
        GoldenCase(
            symbol=row["symbol"],
            exchange=row["exchange"],
            expected_exchange=row["expected_exchange"],
            expected_tick_size=row.get("expected_tick_size"),
            expected_lot_size=row.get("expected_lot_size"),
            expected_security_id=row.get("expected_security_id"),
            expected_instrument_id=row.get("expected_instrument_id"),
            asset=row.get("asset", "equity"),
        )
        for row in data.get("cases", [])
    ]


def verify_golden(broker: str = "paper") -> GoldenReport:
    """Validate broker resolution against the golden reference dataset."""
    report = GoldenReport()
    session = BrokerSession(broker)
    try:
        for case in load_golden_cases():
            passed, detail = _check_case(session, case)
            report.results.append(GoldenResult(case.symbol, passed, detail))
    finally:
        session.close()
    return report


def _resolve(session: BrokerSession, case: GoldenCase) -> Any:
    from datetime import date, timedelta

    expiry = date.today() + timedelta(days=30)
    if case.asset == "index":
        return session.index(case.symbol, exchange=case.exchange)
    if case.asset == "future":
        return session.future(case.symbol, expiry=expiry, exchange=case.exchange)
    if case.asset == "currency":
        return session.currency(case.symbol, exchange=case.exchange)
    if case.asset == "commodity":
        return session.commodity(case.symbol, expiry=expiry, exchange=case.exchange)
    return session.stock(case.symbol, exchange=case.exchange)


def _check_case(session: BrokerSession, case: GoldenCase) -> tuple[bool, str]:
    try:
        inst = _resolve(session, case)
        if inst is None:
            return False, "instrument not resolved"
        if inst.exchange != case.expected_exchange:
            return False, f"exchange {inst.exchange} != {case.expected_exchange}"
        if case.expected_tick_size is not None:
            ts = str(inst.tick_size)
            if ts != case.expected_tick_size:
                return False, f"tick_size {ts} != {case.expected_tick_size}"
        if case.expected_lot_size is not None and inst.lot_size != case.expected_lot_size:
            return False, f"lot_size {inst.lot_size} != {case.expected_lot_size}"
        if case.expected_instrument_id is not None:
            got = str(inst.id)
            if got != case.expected_instrument_id:
                return False, f"instrument_id {got} != {case.expected_instrument_id}"
        if case.expected_security_id is not None:
            meta = getattr(inst, "metadata", None) or getattr(inst, "_metadata", {}) or {}
            sid = meta.get("security_id") or meta.get("securityId")
            if sid is not None and str(sid) != str(case.expected_security_id):
                return False, f"security_id {sid} != {case.expected_security_id}"
        return True, "matches golden"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
