"""Structured connect / session errors — product surface (no raw ENG dumps)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.exceptions import TradeXV2Error


@dataclass
class ConnectError(TradeXV2Error):
    """Raised when ``tradex.connect`` cannot return a usable Session.

    Attributes
    ----------
    code:
        Stable machine code (``OMS_REQUIRED``, ``MISSING_ENV``, …).
    broker_id / mode / phase / trace_id:
        Connection context for logs and CLI.
    remediation:
        Human next step.
    """

    code: str = "CONNECT_FAILED"
    broker_id: str = ""
    mode: str = ""
    phase: str = "Failed"
    trace_id: str = ""
    remediation: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        message: str,
        *,
        code: str = "CONNECT_FAILED",
        broker_id: str = "",
        mode: str = "",
        phase: str = "Failed",
        trace_id: str = "",
        remediation: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.broker_id = broker_id
        self.mode = mode
        self.phase = phase
        self.trace_id = trace_id
        self.remediation = remediation
        self.details = details or {}

    def __str__(self) -> str:
        parts = [f"[{self.code}] {super().__str__()}"]
        if self.remediation:
            parts.append(f"Remediation: {self.remediation}")
        if self.trace_id:
            parts.append(f"trace_id={self.trace_id}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": super().__str__(),
            "broker_id": self.broker_id,
            "mode": self.mode,
            "phase": self.phase,
            "trace_id": self.trace_id,
            "remediation": self.remediation,
            "details": dict(self.details),
        }


# Canonical codes
OMS_REQUIRED = "OMS_REQUIRED"
ORDERS_DISABLED = "ORDERS_DISABLED"
MISSING_ENV = "MISSING_ENV"
AUTH_FAILED = "AUTH_FAILED"
UNKNOWN_BROKER = "UNKNOWN_BROKER"
UNKNOWN_MODE = "UNKNOWN_MODE"
GATEWAY_FAILED = "GATEWAY_FAILED"
ENG_011 = "ENG_011"
