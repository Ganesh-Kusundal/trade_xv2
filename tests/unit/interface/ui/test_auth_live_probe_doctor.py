"""CLI doctor AuthLiveProbeCheck behaviour (probe-only vs force-refresh)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.connection.authenticated_readiness import AuthProbeResult
from interface.ui.commands.doctor.strategies.auth_live_probe import AuthLiveProbeCheck


def test_auth_live_probe_probe_only_never_force_refreshes():
    check = AuthLiveProbeCheck(force_refresh=False, broker="dhan")
    gw = MagicMock()
    gw.funds.return_value = MagicMock()

    with (
        patch.object(check, "_get_gateway", return_value=gw),
        patch(
            "interface.ui.commands.doctor.strategies.auth_live_probe.list_available_brokers",
            return_value=[{"name": "dhan", "available": True}],
        ),
        patch(
            "interface.ui.commands.doctor.strategies.auth_live_probe.authenticated_readiness_probe"
        ) as forced,
    ):
        results = check.execute(None)

    forced.assert_not_called()
    assert results[0].status == "PASS"
    assert "probe-only" in results[0].detail


def test_auth_live_probe_force_refresh_uses_readiness_probe():
    check = AuthLiveProbeCheck(force_refresh=True, broker="dhan")
    gw = MagicMock()

    with (
        patch.object(check, "_get_gateway", return_value=gw),
        patch(
            "interface.ui.commands.doctor.strategies.auth_live_probe.list_available_brokers",
            return_value=[{"name": "dhan", "available": True}],
        ),
        patch(
            "interface.ui.commands.doctor.strategies.auth_live_probe.authenticated_readiness_probe",
            return_value=AuthProbeResult(ok=True, probe_name="dhan.funds", refreshed_token=True),
        ) as forced,
    ):
        results = check.execute(None)

    forced.assert_called_once()
    assert results[0].status == "PASS"
    assert "token refreshed" in results[0].detail
