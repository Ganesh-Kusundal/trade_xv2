"""Dhan TOTP auto-token — probe-before-mint (mirror src token_ensure).

Policy:
1. Prefer store/env token when still valid — never mint.
2. Mint only when missing, expired, or broker_rejected (401/DH-901).
3. Mint at most once per ensure_token; TotpCooldownGuard blocks hammering.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugins.brokers.common.constants import DHAN_COOLDOWN_SECONDS
from plugins.brokers.common.jwt_expiry import JwtExpiry
from plugins.brokers.common.token_lifecycle import TokenBroadcast
from plugins.brokers.common.totp_cooldown import TotpCooldownGuard, TotpRateLimitError
from plugins.brokers.dhan.config import DhanConfig

HttpPost = Callable[[str, dict[str, str], float], dict[str, Any]]


@dataclass
class _TokenRecord:
    access_token: str
    expires_at: float


class DhanTokenStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, access_token: str, expires_at: float) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "expires_at": expires_at,
                    "expires_at_ms": int(expires_at * 1000),
                    "source": "TOTP",
                }
            )
        )

    def load(self) -> str | None:
        rec = self._read()
        return rec.access_token if rec else None

    def is_valid(self, *, now: float | None = None) -> bool:
        rec = self._read()
        if rec is None:
            return False
        return _token_usable(rec.access_token, rec.expires_at, now=now)

    def invalidate(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError:
            pass

    def _read(self) -> _TokenRecord | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            token = str(data["access_token"])
            if "expires_at" in data and data["expires_at"] is not None:
                expires_at = float(data["expires_at"])
            elif "expires_at_ms" in data:
                expires_at = float(data["expires_at_ms"]) / 1000.0
            else:
                jwt_exp = JwtExpiry.parse_expiry_epoch(token)
                expires_at = jwt_exp if jwt_exp > 0 else 0.0
            return _TokenRecord(access_token=token, expires_at=expires_at)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


def _token_usable(
    token: str,
    store_expires_at: float = 0.0,
    *,
    now: float | None = None,
) -> bool:
    if not token:
        return False
    clock = now if now is not None else time.time()
    jwt_exp = JwtExpiry.parse_expiry_epoch(token)
    if jwt_exp > 0:
        return jwt_exp > clock
    if store_expires_at > 0:
        return store_expires_at > clock
    # Non-JWT static token: usable until broker_rejected
    return True


def _default_http_post(url: str, data: dict[str, str], timeout: float) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class DhanTotpClient:
    def __init__(
        self,
        config: DhanConfig,
        *,
        http_post: HttpPost | None = None,
        cooldown: TotpCooldownGuard | None = None,
    ) -> None:
        self._config = config
        self._http_post = http_post or _default_http_post
        self._cooldown = cooldown or TotpCooldownGuard(
            "dhan",
            state_path=config.cooldown_path,
        )

    def generate(self) -> str | None:
        self._cooldown.check_allowed()
        if not self._config.has_totp:
            return None
        try:
            import pyotp
        except ImportError as exc:
            raise RuntimeError("pyotp required for Dhan TOTP — pip install pyotp") from exc

        self._cooldown.record_attempt()
        totp_code = pyotp.TOTP(self._config.totp_secret).now()
        payload = {
            "dhanClientId": self._config.client_id,
            "pin": self._config.pin,
            "totp": totp_code,
        }
        body = self._http_post(self._config.generate_token_url, payload, 15.0)
        message = str(body.get("message", ""))
        if "once every 2 minutes" in message:
            self._cooldown.record_rate_limited()
            raise TotpRateLimitError(
                f"Dhan token rate limit: {message}",
                remaining_seconds=self._cooldown.remaining_cooldown_seconds() or DHAN_COOLDOWN_SECONDS,
            )
        if body.get("status") == "error":
            return None
        data = body.get("data", body)
        token = ""
        if isinstance(data, dict):
            token = str(data.get("accessToken") or data.get("access_token") or "")
        if token:
            self._cooldown.record_success()
            return token
        return None


class DhanTokenManager:
    """Resolve access token: store → env → TOTP (never proactive mint)."""

    def __init__(
        self,
        config: DhanConfig,
        *,
        totp: DhanTotpClient | None = None,
        store: DhanTokenStore | None = None,
    ) -> None:
        self._config = config
        self._store = store or DhanTokenStore(config.token_path)
        self._totp = totp or DhanTotpClient(config)
        self._broadcast = TokenBroadcast()
        self._memory = ""
        if self._store.is_valid():
            self._memory = self._store.load() or ""
        elif config.access_token and _token_usable(config.access_token):
            self._memory = config.access_token

    def register_receiver(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Notified with the new token whenever ensure_token() mints one."""
        return self._broadcast.register(receiver)

    def ensure_token(self, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self._memory = ""
            self._config.access_token = ""
            self._store.invalidate()
        elif self._memory and _token_usable(self._memory):
            # Proactive refresh: check if token is about to expire
            jwt_exp = JwtExpiry.parse_expiry_epoch(self._memory)
            if jwt_exp > 0:
                buffer = self._config.refresh_buffer_seconds
                if jwt_exp - time.time() <= buffer:
                    force_refresh = True  # Trigger proactive refresh
                else:
                    return self._memory  # Token still valid, not about to expire
            else:
                return self._memory  # No JWT expiry, trust usability check
        elif self._store.is_valid():
            token = self._store.load()
            if token:
                self._memory = token
                # Check if stored token is about to expire
                jwt_exp = JwtExpiry.parse_expiry_epoch(token)
                if jwt_exp > 0:
                    buffer = self._config.refresh_buffer_seconds
                    if jwt_exp - time.time() <= buffer:
                        force_refresh = True  # Trigger proactive refresh
                    else:
                        return token  # Token still valid
                else:
                    return token  # No JWT expiry
        elif self._config.access_token and _token_usable(self._config.access_token):
            self._memory = self._config.access_token
            return self._memory

        if self._config.has_totp:
            token = self._totp.generate()
            if token:
                expires_at = JwtExpiry.parse_expiry_epoch(token)
                if expires_at < 0:
                    expires_at = time.time() + self._config.token_ttl_seconds
                self._store.save(token, expires_at=expires_at)
                self._memory = token
                self._config.access_token = token
                self._broadcast.broadcast(token)
                return token
            if force_refresh:
                raise RuntimeError("Dhan force refresh failed: TOTP unavailable or rejected")
        if self._config.access_token and not force_refresh:
            self._memory = self._config.access_token
            return self._memory
        raise RuntimeError("Dhan authenticate failed: no access_token and TOTP unavailable")

    def current(self) -> str:
        return self._memory or self._config.access_token or (self._store.load() or "")
