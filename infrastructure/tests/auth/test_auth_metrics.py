"""Auth metrics and readiness probe instrumentation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.auth.metrics import AuthMetrics
from infrastructure.connection.authenticated_readiness import execute_read_only_probe
from infrastructure.resilience.errors import AuthenticationError


def test_auth_metrics_totp_paths_do_not_raise():
    # Should be safe even if registry is empty / labels exist
    AuthMetrics.totp_reuse("dhan")
    AuthMetrics.totp_mint("dhan")
    AuthMetrics.totp_mint_fail("upstox")
    AuthMetrics.totp_rate_limit("dhan")
    AuthMetrics.probe_ok("upstox")
    AuthMetrics.probe_fail("upstox")
    AuthMetrics.token_rejected("dhan")
    AuthMetrics.api_rate_limit("upstox")


def test_execute_read_only_probe_records_ok():
    gw = MagicMock()
    gw.funds.return_value = MagicMock()
    with patch("infrastructure.auth.metrics.AuthMetrics.probe_ok") as ok:
        result = execute_read_only_probe(gw, "dhan")
    assert result.ok
    ok.assert_called_with("dhan")


def test_execute_read_only_probe_records_fail_and_reject():
    gw = MagicMock()
    gw.funds.side_effect = AuthenticationError("Token rejected: DH-906")
    with (
        patch("infrastructure.auth.metrics.AuthMetrics.probe_fail") as fail,
        patch("infrastructure.auth.metrics.AuthMetrics.token_rejected") as rej,
    ):
        result = execute_read_only_probe(gw, "dhan")
    assert not result.ok
    assert result.token_rejected
    fail.assert_called_with("dhan")
    rej.assert_called_with("dhan")
