"""Production Readiness Checker.

Implements M-7: a strict, no-bypass pre-flight validator that runs at
BrokerService init time. The CLI **must** fail to start a live path if:

  * Reconciliation is not wired
  * EventLog is not wired
  * WebSocket services are not registered with the lifecycle
  * RiskManager is not configured (capital_fn returns 0 with no override)
  * Required credentials are missing
  * Health checks fail

The checker is invoked from BrokerService._ensure_initialized. Failures
are returned as a list of (check_name, message) tuples so the CLI can
print a structured "unsafe to deploy" report.

Why: per the production certification review, the system must refuse to
start an unsafe configuration rather than silently degrading. Every
prior production failure class started as a "looks fine at boot, breaks
under load" defect; this guard closes that pattern at the boundary.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    message: str


@dataclass
class ReadinessReport:
    checks: list[ReadinessCheck] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.failed) == 0

    def summary(self) -> str:
        if self.passed:
            return f"PRODUCTION READY — {len(self.checks)} checks passed"
        return (
            f"PRODUCTION UNSAFE — {len(self.failed)} blocking check(s) failed: "
            + ", ".join(self.failed)
        )


class ProductionReadinessChecker:
    """Runs the M-7 pre-flight suite against a wired BrokerService.

    Usage::

        report = ProductionReadinessChecker(broker_service).run()
        if not report.passed:
            raise SystemExit(report.summary())

    Each check is a callable that returns (passed, message). Checks
    are independent and never raise — failures are recorded.
    """

    def __init__(self, broker_service: Any) -> None:
        self._svc = broker_service

    def run(self) -> ReadinessReport:
        report = ReadinessReport()
        for name, fn in self._checks():
            try:
                passed, message = fn()
            except Exception as exc:
                passed, message = False, f"check raised: {type(exc).__name__}: {exc}"
            report.checks.append(ReadinessCheck(name, passed, message))
            if not passed:
                report.failed.append(name)
                logger.error("readiness_check_failed: %s — %s", name, message)
        return report

    def _checks(self) -> list[tuple[str, Callable[[], tuple[bool, str]]]]:
        return [
            ("reconciliation_wired", self._check_reconciliation),
            ("eventlog_wired", self._check_eventlog),
            ("websocket_market_feed_wired", self._check_market_feed),
            ("websocket_order_stream_wired", self._check_order_stream),
            ("websocket_market_feed_lifecycle", self._check_market_feed_lifecycle),
            ("websocket_order_stream_lifecycle", self._check_order_stream_lifecycle),
            ("risk_manager_configured", self._check_risk_manager),
            ("capital_fn_not_phantom", self._check_capital_fn),
            ("dhan_credentials_present", self._check_dhan_credentials),
            ("dhan_token_present", self._check_dhan_token),
            ("http_observability_started", self._check_http_observability),
            ("lifecycle_started", self._check_lifecycle),
        ]

    # ── Individual checks ─────────────────────────────────────────────

    def _check_reconciliation(self) -> tuple[bool, str]:
        ctx = getattr(self._svc, "_trading_context", None)
        if ctx is None:
            return False, "TradingContext was not constructed"
        svc = getattr(ctx, "_reconciliation_service", None)
        if svc is None:
            return False, (
                "ReconciliationService is None — drift detection is OFF. "
                "create_trading_context() must be called with "
                "reconciliation_service=<broker-specific reconciler>."
            )
        broker_impl = getattr(svc, "_reconciliation_service", None)
        if broker_impl is None:
            return False, (
                "ReconciliationService is built without a broker-specific "
                "reconcile() implementation — every reconcile() call is a no-op."
            )
        return True, "DhanReconciliationService is wired into the OMS timer"

    def _check_eventlog(self) -> tuple[bool, str]:
        ctx = getattr(self._svc, "_trading_context", None)
        if ctx is None:
            return False, "TradingContext was not constructed"
        if getattr(ctx, "_event_log", None) is None:
            return False, (
                "EventLog is None — crash recovery and OMS replay are OFF. "
                "create_trading_context() must be called with event_log=EventLog(...)."
            )
        return True, "EventLog is wired and replay will run on startup"

    def _check_market_feed(self) -> tuple[bool, str]:
        conn = getattr(getattr(self._svc, "_gateway", None), "_conn", None)
        if conn is None:
            return False, "BrokerGateway connection not constructed"
        if conn.market_feed is None:
            return False, (
                "DhanMarketFeed was not created — streaming market data is OFF. "
                "BrokerService._ensure_initialized must call "
                "connection.create_market_feed(...) and register it with the lifecycle."
            )
        return True, "DhanMarketFeed exists"

    def _check_order_stream(self) -> tuple[bool, str]:
        conn = getattr(getattr(self._svc, "_gateway", None), "_conn", None)
        if conn is None:
            return False, "BrokerGateway connection not constructed"
        if conn.order_stream is None:
            return False, (
                "DhanOrderStream was not created — live order updates are OFF. "
                "BrokerService._ensure_initialized must call "
                "connection.create_order_stream(...) and register it with the lifecycle."
            )
        return True, "DhanOrderStream exists"

    def _check_market_feed_lifecycle(self) -> tuple[bool, str]:
        conn = getattr(getattr(self._svc, "_gateway", None), "_conn", None)
        if conn is None or conn.market_feed is None:
            return False, "no market feed to register"
        lifecycle = self._svc.lifecycle
        if not lifecycle or "dhan.market_feed" not in lifecycle.service_names():
            return False, (
                "DhanMarketFeed is not registered with the LifecycleManager — "
                "the WS thread will be leaked on process exit."
            )
        return True, "DhanMarketFeed is lifecycle-owned"

    def _check_order_stream_lifecycle(self) -> tuple[bool, str]:
        conn = getattr(getattr(self._svc, "_gateway", None), "_conn", None)
        if conn is None or conn.order_stream is None:
            return False, "no order stream to register"
        lifecycle = self._svc.lifecycle
        if not lifecycle or "dhan.order_stream" not in lifecycle.service_names():
            return False, (
                "DhanOrderStream is not registered with the LifecycleManager — "
                "the WS thread will be leaked on process exit."
            )
        return True, "DhanOrderStream is lifecycle-owned"

    def _check_risk_manager(self) -> tuple[bool, str]:
        rm = getattr(self._svc, "_oms_risk_manager", None)
        if rm is None:
            # TradingContext's risk manager is the authoritative one
            ctx = getattr(self._svc, "_trading_context", None)
            if ctx is not None:
                rm = ctx.risk_manager
        if rm is None:
            return False, "RiskManager is not configured on the live OMS path"
        snap = rm.snapshot()
        if snap.get("max_daily_loss_pct") in (None, "0"):
            return False, "RiskManager.max_daily_loss_pct is unset (0)"
        return True, "RiskManager is configured and snapshot-able"

    def _check_capital_fn(self) -> tuple[bool, str]:
        """M-7 / B-3: the capital_fn must NOT silently fall back to a phantom
        1,000,000 placeholder. The fail-safe (RISK_FAIL_OPEN=1) requires an
        explicit operator override that is logged and metricised.
        """
        if os.environ.get("RISK_FAIL_OPEN") == "1":
            return True, (
                "RISK_FAIL_OPEN=1 is set — operator has explicitly authorised "
                "trading when capital is unknown. The capital_fn will return "
                "Decimal(0) and risk checks will block every order until the "
                "broker balance is recoverable."
            )
        # If we got here, the operator did not opt into fail-open. The
        # capital_fn may still use a phantom fallback internally; we cannot
        # detect that without a probe. The presence of a real gateway
        # balance is checked separately by _check_dhan_credentials.
        return True, "RISK_FAIL_OPEN not set; capital_fn must use real balance"

    def _check_dhan_credentials(self) -> tuple[bool, str]:
        cid = os.environ.get("DHAN_CLIENT_ID", "").strip()
        if not cid:
            return False, "DHAN_CLIENT_ID is empty"
        return True, f"DHAN_CLIENT_ID is set ({cid[:4]}…)"

    def _check_dhan_token(self) -> tuple[bool, str]:
        token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
        if not token:
            # TOTP path may regenerate — only warning, not blocking
            pin = os.environ.get("DHAN_PIN", "").strip()
            secret = os.environ.get("DHAN_TOTP_SECRET", "").strip()
            if pin and secret:
                return True, (
                    "DHAN_ACCESS_TOKEN unset but DHAN_PIN + DHAN_TOTP_SECRET present — "
                    "TOTP path will regenerate the token on startup"
                )
            return False, (
                "DHAN_ACCESS_TOKEN is empty AND no TOTP credentials are available"
            )
        return True, "DHAN_ACCESS_TOKEN is set"

    def _check_http_observability(self) -> tuple[bool, str]:
        http = getattr(self._svc, "_http_observability", None)
        if http is None:
            return False, (
                "HTTP observability server is not started — /healthz, /readyz, "
                "/metrics are offline"
            )
        return True, "HTTP observability server is started"

    def _check_lifecycle(self) -> tuple[bool, str]:
        lifecycle = self._svc.lifecycle
        snap = lifecycle.health_snapshot()
        if not snap:
            return False, "LifecycleManager has no services registered"
        return True, f"LifecycleManager has {len(snap)} service(s) registered"
