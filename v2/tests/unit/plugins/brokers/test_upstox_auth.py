"""Upstox auth — token store + refresh + TOTP path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plugins.brokers.common.totp_cooldown import TotpCooldownGuard, TotpRateLimitError
from plugins.brokers.upstox.auth import UpstoxTokenManager, UpstoxTokenStore
from plugins.brokers.upstox.config import UpstoxConfig


def test_upstox_token_store_roundtrip(tmp_path: Path) -> None:
    store = UpstoxTokenStore(tmp_path / "u.json")
    store.save(access_token="atok", refresh_token="rtok", expires_at=9_999_999_999.0)
    snap = store.load()
    assert snap is not None
    assert snap.access_token == "atok"
    assert snap.refresh_token == "rtok"
    assert store.is_valid()


def test_ensure_token_uses_existing(tmp_path: Path) -> None:
    cfg = UpstoxConfig(
        client_id="c",
        client_secret="s",
        access_token="STATIC",
        token_path=tmp_path / "u.json",
        cooldown_path=tmp_path / "cd.json",
    )
    mgr = UpstoxTokenManager(cfg)
    assert mgr.ensure_token() == "STATIC"


def test_ensure_token_refresh_when_expired(tmp_path: Path) -> None:
    store = UpstoxTokenStore(tmp_path / "u.json")
    store.save(access_token="old", refresh_token="refresh-me", expires_at=1.0)
    cfg = UpstoxConfig(
        client_id="c",
        client_secret="s",
        access_token="",
        refresh_token="",
        token_path=tmp_path / "u.json",
        cooldown_path=tmp_path / "cd.json",
    )

    def fake_refresh(refresh_token: str) -> dict[str, Any]:
        assert refresh_token == "refresh-me"
        return {
            "access_token": "fresh",
            "refresh_token": "refresh-me",
            "expires_in": 86400,
        }

    mgr = UpstoxTokenManager(cfg, refresh_fn=fake_refresh)
    assert mgr.ensure_token() == "fresh"
    assert store.load() is not None
    assert store.load().access_token == "fresh"  # type: ignore[union-attr]


def test_ensure_token_reuses_valid_env_jwt_without_mint(tmp_path: Path) -> None:
    """Probe-before-mint: valid env JWT must not call TOTP."""
    import base64
    import json
    import time

    def _jwt(exp: float) -> str:
        h = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        p = base64.urlsafe_b64encode(json.dumps({"exp": int(exp)}).encode()).decode().rstrip("=")
        return f"{h}.{p}.sig"

    token = _jwt(time.time() + 3600)
    cfg = UpstoxConfig(
        client_id="c",
        client_secret="s",
        access_token=token,
        mobile="9999999999",
        pin="1212",
        totp_secret="JBSWY3DPEHPK3PXP",
        token_path=tmp_path / "u.json",
        cooldown_path=tmp_path / "cd.json",
    )
    mgr = UpstoxTokenManager(cfg)

    def boom() -> dict[str, Any]:
        raise AssertionError("must not mint when env JWT valid")

    mgr._totp_generate = boom  # type: ignore[method-assign]
    assert mgr.ensure_token() == token


def test_force_refresh_does_not_reuse_rejected_env_jwt(tmp_path: Path) -> None:
    import base64
    import json
    import time

    def _jwt(exp: float) -> str:
        h = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        p = base64.urlsafe_b64encode(json.dumps({"exp": int(exp)}).encode()).decode().rstrip("=")
        return f"{h}.{p}.sig"

    bad = _jwt(time.time() + 3600)
    cfg = UpstoxConfig(
        client_id="c",
        client_secret="s",
        access_token=bad,
        mobile="9999999999",
        pin="1212",
        totp_secret="JBSWY3DPEHPK3PXP",
        token_path=tmp_path / "u.json",
        cooldown_path=tmp_path / "cd.json",
    )
    guard = TotpCooldownGuard("upstox", 600.0, tmp_path / "cd.json")
    mgr = UpstoxTokenManager(cfg, cooldown=guard)
    mgr._totp_generate = lambda: {"access_token": "minted", "refresh_token": "", "expires_in": 60}  # type: ignore[method-assign]
    assert mgr.ensure_token(force_refresh=True) == "minted"


def test_totp_generate_blocked_by_cooldown(tmp_path: Path) -> None:
    cfg = UpstoxConfig(
        client_id="c",
        client_secret="s",
        mobile="9999999999",
        pin="1212",
        totp_secret="JBSWY3DPEHPK3PXP",
        token_path=tmp_path / "u.json",
        cooldown_path=tmp_path / "cd.json",
    )
    guard = TotpCooldownGuard("upstox", 600.0, tmp_path / "cd.json")
    guard.record_rate_limited()
    mgr = UpstoxTokenManager(cfg, cooldown=guard)

    def boom() -> dict[str, Any]:
        raise AssertionError("should not call totp")

    mgr._totp_generate = boom  # type: ignore[method-assign]
    with pytest.raises(TotpRateLimitError):
        mgr.generate_via_totp()
