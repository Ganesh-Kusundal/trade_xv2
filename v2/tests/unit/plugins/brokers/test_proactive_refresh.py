"""Tests for proactive token refresh behavior."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import pytest

from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.upstox.auth import UpstoxTokenManager
from plugins.brokers.upstox.config import UpstoxConfig


def _make_jwt(exp: float) -> str:
    """Create a minimal JWT with the given expiry."""
    h = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"exp": int(exp)}).encode()).decode().rstrip("=")
    return f"{h}.{p}.sig"


class TestDhanProactiveRefresh:
    """DhanTokenManager should trigger proactive refresh when token is about to expire."""

    def test_refresh_buffer_seconds_default(self) -> None:
        """DhanConfig should have refresh_buffer_seconds default of 300."""
        cfg = DhanConfig(
            client_id="c",
            access_token="",
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=Path("/tmp/test.json"),
        )
        assert cfg.refresh_buffer_seconds == 300  # 5 minutes

    def test_token_not_about_to_expire_returns_immediately(self, tmp_path: Path) -> None:
        """Token with expiry > buffer should be returned without refresh."""
        token = _make_jwt(time.time() + 3600)  # 1 hour from now
        cfg = DhanConfig(
            client_id="c",
            access_token=token,
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=tmp_path / "d.json",
        )
        mgr = DhanTokenManager(cfg)

        def boom() -> str:
            raise AssertionError("should not refresh")

        mgr._totp.generate = boom  # type: ignore[method-assign]
        result = mgr.ensure_token()
        assert result == token

    def test_token_about_to_expire_triggers_refresh(self, tmp_path: Path) -> None:
        """Token with expiry <= buffer should trigger refresh."""
        token = _make_jwt(time.time() + 60)  # 1 minute from now (within 5min buffer)
        cfg = DhanConfig(
            client_id="c",
            access_token=token,
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=tmp_path / "d.json",
        )
        mgr = DhanTokenManager(cfg)

        refreshed_token = _make_jwt(time.time() + 86400)
        mgr._totp.generate = lambda: refreshed_token  # type: ignore[method-assign]
        result = mgr.ensure_token()
        assert result == refreshed_token


class TestUpstoxProactiveRefresh:
    """UpstoxTokenManager should trigger proactive refresh when token is about to expire."""

    def test_refresh_buffer_seconds_default(self) -> None:
        """UpstoxConfig should have refresh_buffer_seconds default of 1800."""
        cfg = UpstoxConfig(
            client_id="c",
            client_secret="s",
            access_token="",
            mobile="9999999999",
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=Path("/tmp/test.json"),
        )
        assert cfg.refresh_buffer_seconds == 1800  # 30 minutes

    def test_token_not_about_to_expire_returns_immediately(self, tmp_path: Path) -> None:
        """Token with expiry > buffer should be returned without refresh."""
        token = _make_jwt(time.time() + 7200)  # 2 hours from now
        cfg = UpstoxConfig(
            client_id="c",
            client_secret="s",
            access_token=token,
            mobile="9999999999",
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=tmp_path / "u.json",
        )
        mgr = UpstoxTokenManager(cfg)

        def boom() -> dict[str, Any]:
            raise AssertionError("should not refresh")

        mgr._totp_generate = boom  # type: ignore[method-assign]
        result = mgr.ensure_token()
        assert result == token

    def test_token_about_to_expire_triggers_refresh(self, tmp_path: Path) -> None:
        """Token with expiry <= buffer should trigger refresh."""
        token = _make_jwt(time.time() + 600)  # 10 minutes from now (within 30min buffer)
        cfg = UpstoxConfig(
            client_id="c",
            client_secret="s",
            access_token=token,
            mobile="9999999999",
            pin="1212",
            totp_secret="JBSWY3DPEHPK3PXP",
            token_path=tmp_path / "u.json",
            cooldown_path=tmp_path / "cd.json",  # Fresh cooldown path
        )
        mgr = UpstoxTokenManager(cfg)

        refreshed_token = _make_jwt(time.time() + 86400)
        mgr._totp_generate = lambda: {"access_token": refreshed_token, "refresh_token": "", "expires_in": 86400}  # type: ignore[method-assign]
        result = mgr.ensure_token()
        assert result == refreshed_token
