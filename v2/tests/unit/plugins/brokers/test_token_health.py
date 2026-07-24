"""Regression: token-expiry health signal (Improvement B).

Gateway/Connection expose token_status() so the app can warn before a
mid-session expiry instead of only learning about it on the next 401.
"""

from __future__ import annotations

import base64
import json
import sys
import time

if sys.path.insert(0, "src") or True:  # ensure src importable under uv
    pass

from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.upstox.auth import UpstoxTokenManager


def _make_jwt(exp_offset: float) -> str:
    """Build a structurally-valid JWT (header.payload.signature) with exp."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time() + exp_offset)}).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def test_dhan_expiring_soon_true_when_within_buffer() -> None:
    # exp 60s ahead, refresh_buffer 300s -> expiring soon
    mgr = DhanTokenManager.__new__(DhanTokenManager)
    mgr._memory = _make_jwt(60)
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    assert mgr.is_expiring_soon() is True


def test_dhan_expiring_soon_false_when_far() -> None:
    mgr = DhanTokenManager.__new__(DhanTokenManager)
    mgr._memory = _make_jwt(3600)
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    assert mgr.is_expiring_soon() is False


def test_dhan_token_status_shape() -> None:
    mgr = DhanTokenManager.__new__(DhanTokenManager)
    mgr._memory = _make_jwt(3600)
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    status = mgr.token_status()
    assert status["has_token"] is True
    assert isinstance(status["expires_at"], (int, float))
    assert status["expiring_soon"] is False


def test_upstox_expiring_soon_true_when_within_buffer() -> None:
    mgr = UpstoxTokenManager.__new__(UpstoxTokenManager)
    mgr._memory = _make_jwt(60)
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    assert mgr.is_expiring_soon() is True


def test_upstox_expiring_soon_false_when_far() -> None:
    mgr = UpstoxTokenManager.__new__(UpstoxTokenManager)
    mgr._memory = _make_jwt(3600)
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    assert mgr.is_expiring_soon() is False


def test_no_token_is_expiring_soon() -> None:
    mgr = DhanTokenManager.__new__(DhanTokenManager)
    mgr._memory = ""
    mgr._store = _NoStore()
    mgr._config = _Cfg(refresh_buffer_seconds=300)
    assert mgr.is_expiring_soon() is True


class _Cfg:
    def __init__(self, refresh_buffer_seconds: float = 300.0) -> None:
        self.refresh_buffer_seconds = refresh_buffer_seconds
        self.access_token = ""


class _NoStore:
    def load(self):
        return None
