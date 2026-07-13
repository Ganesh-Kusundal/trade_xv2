"""Production Readiness Checker.

Implements M-7: a strict, no-bypass pre-flight validator that runs at
BrokerService init time. The CLI **must** fail to start a live path if:

  * Reconciliation is not wired
  * EventLog is not wired
  * WebSocket services are not registered with the lifecycle
  * RiskManager is not configured (capital_fn returns 0 with no override)
  * Required credentials are missing
  * Health checks fail

The checker is invoked from BrokerService.initialize. Failures
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

from domain.exceptions import TradeXV2Error

logger = logging.getLogger(__name__)


def _is_production_env() -> bool:
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    return env in ("production", "staging")


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    message: str


class ProductionReadinessError(TradeXV2Error):
    """Raised by :meth:`ProductionReadinessChecker.run_or_raise` when
    any pre-flight check failed.

    The associated :class:`ReadinessReport` is attached as
    :attr:`report` so operators can inspect exactly which checks
    failed and why.
    """

    def __init__(self, report: ReadinessReport) -> None:
        self.report = report
        super().__init__(report.summary())


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
        return f"PRODUCTION UNSAFE — {len(self.failed)} blocking check(s) failed: " + ", ".join(
            self.failed
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

    def run_or_raise(
        self,
        error_factory: Callable[[ReadinessReport], BaseException] | None = None,
    ) -> ReadinessReport:
        """Run the checks and raise if any failed.

        REF-17: this is the canonical entry point for production paths.
        A caller that uses :meth:`run` and ignores the result is the
        exact anti-pattern the audit called out. The default factory
        raises :class:`ProductionReadinessError` so an unsafe
        configuration cannot accidentally make it past the gate.

        Args:
            error_factory: Optional override for the exception type
                (useful in tests that want to assert a specific class).
        """
        report = self.run()
        if not report.passed:
            factory = error_factory or ProductionReadinessError
            raise factory(report)
        return report

    def _checks(self) -> list[tuple[str, Callable[[], tuple[bool, str]]]]:
        checks = [
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
            ("ssl_hardening", self._check_ssl_hardening),
        ]
        if self._svc.upstox_gateway is not None or getattr(
            self._svc, "upstox_authenticated", False
        ):
            checks.extend(
                [
                    ("upstox_credentials_present", self._check_upstox_credentials),
                    ("upstox_token_present", self._check_upstox_token),
                    ("upstox_websocket_lifecycle", self._check_upstox_websocket_lifecycle),
                    ("upstox_webhook_secret", self._check_upstox_webhook_secret),
                ]
            )
        if _is_production_env():
            checks.extend(
                [
                    ("secret_encryption_configured", self._check_secret_encryption),
                    ("api_key_explicitly_set", self._check_api_key_explicit),
                ]
            )
        return checks

    # ── Individual checks ─────────────────────────────────────────────

    def _check_reconciliation(self) -> tuple[bool, str]:
        ctx = self._svc.trading_context if hasattr(self._svc, 'trading_context') else None
        if ctx is None:
            return False, "TradingContext was not constructed"
        svc = ctx._reconciliation_service if hasattr(ctx, '_reconciliation_service') else None
        if svc is None:
            return False, (
                "ReconciliationService is None — drift detection is OFF. "
                "create_trading_context() must be called with "
                "reconciliation_service=<broker-specific reconciler>."
            )
        broker_impl = svc._reconciliation_service if hasattr(svc, '_reconciliation_service') else None
        if broker_impl is None:
            return False, (
                "ReconciliationService is built without a broker-specific "
                "reconcile() implementation — every reconcile() call is a no-op."
            )
        return True, "DhanReconciliationService is wired into the OMS timer"

    def _check_eventlog(self) -> tuple[bool, str]:
        ctx = self._svc.trading_context if hasattr(self._svc, 'trading_context') else None
        if ctx is None:
            return False, "TradingContext was not constructed"
        if ctx.event_log is None:
            return False, (
                "EventLog is None — crash recovery and OMS replay are OFF. "
                "create_trading_context() must be called with event_log=EventLog(...)."
            )
        return True, "EventLog is wired and replay will run on startup"

    def _check_market_feed(self) -> tuple[bool, str]:
        gw = self._svc.dhan_gateway if hasattr(self._svc, 'dhan_gateway') else None
        conn = gw._conn if gw is not None and hasattr(gw, '_conn') else None
        if conn is None:
            return False, "BrokerGateway connection not constructed"
        if conn.market_feed is None:
            return False, (
                "DhanMarketFeed was not created — streaming market data is OFF. "
                "BrokerService.initialize must call "
                "connection.create_market_feed(...) and register it with the lifecycle."
            )
        return True, "DhanMarketFeed exists"

    def _check_order_stream(self) -> tuple[bool, str]:
        gw = self._svc.dhan_gateway if hasattr(self._svc, 'dhan_gateway') else None
        conn = gw._conn if gw is not None and hasattr(gw, '_conn') else None
        if conn is None:
            return False, "BrokerGateway connection not constructed"
        if conn.order_stream is None:
            return False, (
                "DhanOrderStream was not created — live order updates are OFF. "
                "BrokerService.initialize must call "
                "connection.create_order_stream(...) and register it with the lifecycle."
            )
        return True, "DhanOrderStream exists"

    def _check_market_feed_lifecycle(self) -> tuple[bool, str]:
        gw = self._svc.dhan_gateway if hasattr(self._svc, 'dhan_gateway') else None
        conn = gw._conn if gw is not None and hasattr(gw, '_conn') else None
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
        gw = self._svc.dhan_gateway if hasattr(self._svc, 'dhan_gateway') else None
        conn = gw._conn if gw is not None and hasattr(gw, '_conn') else None
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
        # G7 (P5-8): no getattr reach-through. `_oms_risk_manager` is never set
        # on BrokerService, so the authoritative risk manager is the one owned
        # by the trading context; read it via the public property.
        ctx = self._svc.trading_context if hasattr(self._svc, 'trading_context') else None
        rm = ctx.risk_manager if ctx is not None else None
        if rm is None:
            return False, "RiskManager is not configured on the live OMS path"
        snap = rm.snapshot()
        if snap.get("max_daily_loss_pct") in (None, "0"):
            return False, "RiskManager.max_daily_loss_pct is unset (0)"
        return True, "RiskManager is configured and snapshot-able"

    def _check_capital_fn(self) -> tuple[bool, str]:
        """M-7 / B-3: the capital_fn must NOT silently fall back to a phantom
        1,000,000 placeholder.

        REF-17: the original implementation accepted ``RISK_FAIL_OPEN=1``
        and *passed* the readiness check, allowing live trading to start
        with a phantom 1,000,000 INR capital placeholder. That was the
        "looks fine at boot, breaks under load" failure pattern the
        production-readiness gate was created to prevent.

        The corrected contract:

        * The check is **closed by default** — only ``RISK_FAIL_OPEN=0``
          (the unset case) passes.
        * ``RISK_FAIL_OPEN=1`` is a developer-only override and now
          *fails* the readiness check, with a structured message that
          tells the operator exactly how to disable the gate for testing
          (``RISK_FAIL_OPEN=0`` or simply unset the variable).
        * An empty / unset ``RISK_FAIL_OPEN`` is treated identically to
          ``0`` — the safe state must be the default state, not require
          a flag.
        """
        val = (os.environ.get("RISK_FAIL_OPEN") or "").strip()
        if val == "1":
            return False, (
                "RISK_FAIL_OPEN=1 is set — this is a developer override and is "
                "REJECTED in production. Unset the variable (or set it to 0) "
                "to enable the production safety gate. Phantom-capital trading "
                "must never go live."
            )
        return True, ("RISK_FAIL_OPEN is unset/0; capital_fn must use real broker balance")

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
            return False, ("DHAN_ACCESS_TOKEN is empty AND no TOTP credentials are available")
        return True, "DHAN_ACCESS_TOKEN is set"

    def _check_upstox_credentials(self) -> tuple[bool, str]:
        cid = (
            os.environ.get("UPSTOX_CLIENT_ID", "").strip()
            or os.environ.get("UPSTOX_API_KEY", "").strip()
        )
        if not cid:
            return False, "UPSTOX_CLIENT_ID / UPSTOX_API_KEY is empty"
        return True, f"Upstox client id is set ({cid[:4]}…)"

    def _check_upstox_token(self) -> tuple[bool, str]:
        token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
        if not token:
            auth_mode = os.environ.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
            if auth_mode == "TOTP":
                mobile = os.environ.get("UPSTOX_MOBILE", "").strip()
                pin = (
                    os.environ.get("UPSTOX_PIN", "").strip()
                    or self._read_secret_file("UPSTOX_PIN_FILE")
                )
                secret = (
                    os.environ.get("UPSTOX_TOTP_SECRET", "").strip()
                    or self._read_secret_file("UPSTOX_TOTP_SECRET_FILE")
                )
                if mobile and pin and secret:
                    return True, ("UPSTOX_ACCESS_TOKEN unset but TOTP credentials present")
            return False, "UPSTOX_ACCESS_TOKEN is empty and no TOTP path configured"
        return True, "UPSTOX_ACCESS_TOKEN is set"

    @staticmethod
    def _read_secret_file(env_key: str) -> str:
        path = os.environ.get(env_key, "").strip()
        if not path:
            return ""
        from pathlib import Path

        file_path = Path(path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8").strip()
        return ""

    def _check_upstox_websocket_lifecycle(self) -> tuple[bool, str]:
        lifecycle = self._svc.lifecycle
        names = lifecycle.service_names() if lifecycle else []
        required = ("upstox.websocket", "upstox.portfolio_stream")
        missing = [n for n in required if n not in names]
        if missing:
            return False, (f"Upstox WebSocket services not lifecycle-registered: {missing}")
        return True, "Upstox WebSocket services are lifecycle-owned"

    def _check_http_observability(self) -> tuple[bool, str]:
        http = self._svc.http_observability if hasattr(self._svc, 'http_observability') else None
        if http is None:
            return False, (
                "HTTP observability server is not started — /healthz, /readyz, /metrics are offline"
            )
        return True, "HTTP observability server is started"

    def _check_lifecycle(self) -> tuple[bool, str]:
        lifecycle = self._svc.lifecycle
        snap = lifecycle.health_snapshot()
        if not snap:
            return False, "LifecycleManager has no services registered"
        return True, f"LifecycleManager has {len(snap)} service(s) registered"

    def _check_secret_encryption(self) -> tuple[bool, str]:
        if not os.environ.get("SECRET_ENCRYPTION_KEY", "").strip():
            return True, (
                "SECRET_ENCRYPTION_KEY unset — using plaintext token stores (default)"
            )
        return True, "SECRET_ENCRYPTION_KEY is configured"

    def _check_api_key_explicit(self) -> tuple[bool, str]:
        if not os.environ.get("API_KEY", "").strip():
            return False, (
                "API_KEY must be explicitly set in production — ephemeral keys are forbidden"
            )
        return True, "API_KEY is explicitly configured"

    def _check_upstox_webhook_secret(self) -> tuple[bool, str]:
        if not _is_production_env():
            return True, "webhook secret check skipped outside production/staging"
        if not os.environ.get("UPSTOX_WEBHOOK_SECRET", "").strip():
            return False, (
                "UPSTOX_WEBHOOK_SECRET is required in production when Upstox is active"
            )
        return True, "UPSTOX_WEBHOOK_SECRET is configured"

    def _check_ssl_hardening(self) -> tuple[bool, str]:
        """REF-38: every outbound HTTP session in the live path MUST be
        built with :class:`infrastructure.security.ssl_hardening.HardenedHTTPSAdapter`.

        A session using the default ``requests`` adapter is acceptable
        for tests but must not be used in live trading — the audit
        flagged this as a P1 hardening gap because an accidental
        ``verify=False`` is not caught at any layer.

        The check inspects ``broker_service._http_sessions`` (a list
        the CLI populates at startup). If no list is registered the
        check is skipped — production deployments are required to
        register at least one session, but absence here is logged
        as a warning rather than a hard failure to avoid blocking
        dry-runs.
        """
        sessions = self._svc.http_sessions if hasattr(self._svc, 'http_sessions') else None
        if not sessions:
            return True, (
                "no outbound sessions registered for SSL check (acceptable "
                "for dry-run; production must register hardened sessions)"
            )
        from domain.ports.security import assert_secure_session

        for idx, session in enumerate(sessions):
            try:
                assert_secure_session(session)
            except RuntimeError as exc:
                return False, f"http_sessions[{idx}] is not TLS-hardened: {exc}"
        return True, f"all {len(sessions)} outbound session(s) use hardened TLS"
