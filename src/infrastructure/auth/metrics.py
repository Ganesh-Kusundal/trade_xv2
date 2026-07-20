"""Auth vs API rate-limit metrics — keep login quota separate from trading RPS.

Counters (label: broker):
  auth_totp_mint_total       — successful TOTP / login mints
  auth_totp_mint_fail_total  — mint failures (network, invalid creds)
  auth_totp_reuse_total      — reused valid JWT without mint
  auth_totp_rate_limit_total — local or broker TOTP cooldown / 2-min lock
  auth_probe_ok_total        — read-only auth probe success
  auth_probe_fail_total      — read-only auth probe failure
  auth_token_rejected_total  — broker rejected access token (401/DH-906)
  api_rate_limit_total       — trading/data API rate-limit events (429 / bucket)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_LABELS = ("broker",)


def _lc(name: str, description: str) -> Any:
    try:
        from infrastructure.metrics import metrics_registry

        return metrics_registry.labelled_counter(name, description, _LABELS)
    except Exception as exc:  # pragma: no cover — metrics optional at import
        logger.debug("auth_metrics_unavailable: %s", exc)
        return None


class AuthMetrics:
    """Thin helpers so call sites never hard-depend on Prometheus wiring."""

    @staticmethod
    def _inc(name: str, description: str, broker: str) -> None:
        c = _lc(name, description)
        if c is not None:
            # LabelledCounter.inc(**labels) — not Prometheus-style .labels().inc()
            c.inc(broker=broker.lower())

    @staticmethod
    def totp_mint(broker: str) -> None:
        AuthMetrics._inc("auth_totp_mint_total", "Successful TOTP/login token mints", broker)

    @staticmethod
    def totp_mint_fail(broker: str) -> None:
        AuthMetrics._inc("auth_totp_mint_fail_total", "Failed TOTP/login token mints", broker)

    @staticmethod
    def totp_reuse(broker: str) -> None:
        AuthMetrics._inc("auth_totp_reuse_total", "Valid JWT reused without TOTP mint", broker)

    @staticmethod
    def totp_rate_limit(broker: str) -> None:
        AuthMetrics._inc(
            "auth_totp_rate_limit_total",
            "TOTP/login rate limited (local cooldown or broker)",
            broker,
        )

    @staticmethod
    def probe_ok(broker: str) -> None:
        AuthMetrics._inc("auth_probe_ok_total", "Authenticated read-only probe success", broker)

    @staticmethod
    def probe_fail(broker: str) -> None:
        AuthMetrics._inc("auth_probe_fail_total", "Authenticated read-only probe failure", broker)

    @staticmethod
    def token_rejected(broker: str) -> None:
        AuthMetrics._inc("auth_token_rejected_total", "Broker rejected access token", broker)

    @staticmethod
    def api_rate_limit(broker: str) -> None:
        AuthMetrics._inc(
            "api_rate_limit_total",
            "Trading/data API rate-limit event (distinct from TOTP)",
            broker,
        )


__all__ = ["AuthMetrics"]
