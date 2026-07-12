"""Certification report types — shared by the broker certification suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CertArea(str, Enum):
    """Certification areas every broker must pass."""

    AUTHENTICATION = "Authentication"
    TOKEN_REFRESH = "Token Refresh"
    TOKEN_EXPIRY = "Token Expiry"
    RECONNECT = "Reconnect"
    INSTRUMENT = "Instrument"
    SYMBOL_LOOKUP = "Symbol Lookup"
    INSTRUMENT_LOOKUP = "Instrument Lookup"
    CANONICAL_MAPPING = "Canonical Symbol Mapping"
    SECURITY_ID_MAPPING = "Security ID Mapping"
    REVERSE_MAPPING = "Reverse Mapping"
    MARKET_DATA = "Market Data"
    QUOTE = "Quote"
    LTP = "LTP"
    OHLC = "OHLC"
    DEPTH = "Depth"
    LIVE_STREAM = "Live Stream"
    HISTORICAL = "Historical"
    TF_1M = "Historical 1m"
    TF_5M = "Historical 5m"
    TF_15M = "Historical 15m"
    TF_DAILY = "Historical Daily"
    ORDERS = "Orders"
    ORDER_MARKET = "Order Market"
    ORDER_LIMIT = "Order Limit"
    ORDER_CANCEL = "Order Cancel"
    ORDER_MODIFY = "Order Modify"
    PORTFOLIO = "Portfolio"
    HOLDINGS = "Holdings"
    POSITIONS = "Positions"
    FUNDS = "Funds"
    PERFORMANCE = "Performance"
    QUOTE_LATENCY = "Quote Latency"
    ORDER_LATENCY = "Order Latency"
    SUBSCRIPTION_LATENCY = "Subscription Latency"
    RECOVERY = "Recovery"
    DISCONNECT = "Disconnect"
    SESSION_RECOVERY = "Session Recovery"
    RATE_LIMITS = "Rate Limits"
    RATE_BURST = "Rate Burst"
    RATE_SUSTAINED = "Rate Sustained"
    CAPABILITY_MATRIX = "Capability Matrix"


@dataclass
class CertResult:
    area: CertArea
    passed: bool
    detail: str = ""
    latency_ms: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "area": self.area.value,
            "passed": self.passed,
            "detail": self.detail,
            "latency_ms": self.latency_ms,
        }


@dataclass
class CertificationReport:
    broker_id: str
    results: list[CertResult] = field(default_factory=list)

    def add(self, result: CertResult) -> CertResult:
        self.results.append(result)
        return result

    @property
    def is_certified(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def print_report(self) -> None:
        print(f"Certification — broker '{self.broker_id}':")
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lat = f" ({r.latency_ms}ms)" if r.latency_ms is not None else ""
            print(f"  [{mark}] {r.area.value}: {r.detail}{lat}")
        print(f"Overall: {self.passed}/{self.total} passed -> "
              f"{'CERTIFIED' if self.is_certified else 'NOT CERTIFIED'}")

    def to_dict(self, *, live: bool = False) -> dict[str, Any]:
        from brokers.certification.schema_v2 import (
            SCHEMA_VERSION,
            resolve_status,
            resolve_tier,
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "broker_id": self.broker_id,
            "tier": resolve_tier(self.broker_id, live=live),
            "status": resolve_status(passed=self.is_certified),
            "is_certified": self.is_certified,
            "passed": self.passed,
            "total": self.total,
            "results": [r.as_dict() for r in self.results],
        }