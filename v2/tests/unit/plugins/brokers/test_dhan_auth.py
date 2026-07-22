"""Dhan auth — TOTP auto-token with cooldown + JSON token store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plugins.brokers.common.totp_cooldown import TotpCooldownGuard, TotpRateLimitError
from plugins.brokers.dhan.auth import DhanTokenStore, DhanTotpClient
from plugins.brokers.dhan.config import DhanConfig


def test_token_store_roundtrip(tmp_path: Path) -> None:
    store = DhanTokenStore(tmp_path / "token.json")
    store.save("abc-token", expires_at=9_999_999_999.0)
    assert store.load() == "abc-token"
    assert store.is_valid()


def test_token_store_expired(tmp_path: Path) -> None:
    store = DhanTokenStore(tmp_path / "token.json")
    store.save("old", expires_at=1.0)
    assert store.is_valid() is False


def test_totp_generate_posts_credentials(tmp_path: Path) -> None:
    cfg = DhanConfig(
        client_id="CID",
        pin="1234",
        totp_secret="JBSWY3DPEHPK3PXP",
        access_token="",
        token_path=tmp_path / "t.json",
        cooldown_path=tmp_path / "cd.json",
    )
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, data: dict[str, str], timeout: float) -> dict[str, Any]:
        calls.append({"url": url, "data": data})
        return {"status": "success", "data": {"accessToken": "NEWTOK"}}

    client = DhanTotpClient(cfg, http_post=fake_post, cooldown=TotpCooldownGuard("dhan", 1.0, tmp_path / "cd.json"))
    token = client.generate()
    assert token == "NEWTOK"
    assert calls[0]["data"]["dhanClientId"] == "CID"
    assert "totp" in calls[0]["data"]


def test_totp_rate_limit_message_raises(tmp_path: Path) -> None:
    cfg = DhanConfig(
        client_id="CID",
        pin="1234",
        totp_secret="JBSWY3DPEHPK3PXP",
        token_path=tmp_path / "t.json",
        cooldown_path=tmp_path / "cd.json",
    )

    def fake_post(url: str, data: dict[str, str], timeout: float) -> dict[str, Any]:
        return {"status": "error", "message": "You can generate token only once every 2 minutes"}

    client = DhanTotpClient(cfg, http_post=fake_post, cooldown=TotpCooldownGuard("dhan", 60.0, tmp_path / "cd.json"))
    with pytest.raises(TotpRateLimitError):
        client.generate()
