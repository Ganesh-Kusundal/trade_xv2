"""Unit tests for doctor auth CLI flags."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from interface.ui.commands.doctor import run


def test_doctor_auth_flag_routes_to_auth_doctor():
    console = MagicMock()
    svc = MagicMock()
    with patch("interface.ui.commands.doctor.run_auth_doctor") as auth_run:
        run(["auth"], svc, console)
    auth_run.assert_called_once()
    kwargs = auth_run.call_args.kwargs
    assert kwargs.get("force_refresh") is False


def test_doctor_auth_force_refresh_flag():
    console = MagicMock()
    svc = MagicMock()
    with patch("interface.ui.commands.doctor.run_auth_doctor") as auth_run:
        run(["auth", "--force-refresh", "--broker", "dhan"], svc, console)
    auth_run.assert_called_once()
    kwargs = auth_run.call_args.kwargs
    assert kwargs.get("force_refresh") is True
    assert kwargs.get("broker") == "dhan"
