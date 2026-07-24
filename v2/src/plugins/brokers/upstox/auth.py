"""Upstox token lifecycle — probe-before-mint (mirror src token_ensure / bootstrap_totp_if_needed).

Policy:
1. Reuse memory / store / env JWT when still valid — never mint.
2. Mint only when missing, expired, or broker_rejected (401).
3. Mint at most once per ensure_token call; TotpCooldownGuard blocks hammering.
4. Persist with JWT ``exp`` when available.
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

from plugins.brokers.common.constants import DEFAULT_TOKEN_TTL_SECONDS, UPSTOX_COOLDOWN_SECONDS
from plugins.brokers.common.jwt_expiry import JwtExpiry
from plugins.brokers.common.token_lifecycle import TokenBroadcast
from plugins.brokers.common.totp_cooldown import TotpCooldownGuard, TotpRateLimitError
from plugins.brokers.upstox.config import UpstoxConfig

RefreshFn = Callable[[str], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TokenSnapshot:
    access_token: str
    refresh_token: str
    expires_at: float  # unix seconds


class UpstoxTokenStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, *, access_token: str, refresh_token: str, expires_at: float) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Dual-write expires_at + expires_at_ms so v1/v2 stores interoperate
        self._path.write_text(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token or None,
                    "expires_at": expires_at,
                    "expires_at_ms": int(expires_at * 1000),
                    "issued_at_ms": int(time.time() * 1000),
                    "source": "TOTP",
                }
            )
        )

    def load(self) -> TokenSnapshot | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            token = str(data.get("access_token") or "")
            if not token:
                return None
            if "expires_at" in data and data["expires_at"] is not None:
                expires_at = float(data["expires_at"])
            elif "expires_at_ms" in data:
                expires_at = float(data["expires_at_ms"]) / 1000.0
            else:
                jwt_exp = JwtExpiry.parse_expiry_epoch(token)
                expires_at = jwt_exp if jwt_exp > 0 else 0.0
            return TokenSnapshot(
                access_token=token,
                refresh_token=str(data.get("refresh_token") or ""),
                expires_at=expires_at,
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def is_valid(self, *, now: float | None = None, buffer: float = 0.0) -> bool:
        snap = self.load()
        if snap is None:
            return False
        return _access_token_usable(snap.access_token, snap.expires_at, now=now, buffer=buffer)

    def invalidate(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError:
            pass


def _access_token_usable(
    token: str,
    store_expires_at: float = 0.0,
    *,
    now: float | None = None,
    buffer: float = 0.0,
) -> bool:
    """Prefer JWT exp; fall back to store expiry. buffer=0 for TOTP (no proactive mint)."""
    if not token:
        return False
    clock = now if now is not None else time.time()
    jwt_exp = JwtExpiry.parse_expiry_epoch(token)
    if jwt_exp > 0:
        return jwt_exp > (clock + buffer)
    # A string that LOOKS like a JWT (3 segments) but can't be
    # decoded is corrupt — reject it so the manager force-refreshes
    # instead of trusting a garbage token until the broker rejects it.
    if JwtExpiry.is_jwt_like(token):
        return False
    if store_expires_at > 0:
        return store_expires_at > (clock + buffer)
    # Non-JWT static token with no expiry: treat as usable until broker_rejected
    return True


def _default_refresh(token_url: str, client_id: str, client_secret: str, redirect_uri: str):
    def _refresh(refresh_token: str) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode()
        req = urllib.request.Request(
            token_url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    return _refresh


def _is_upstox_otp_rate_limit(exc: object) -> bool:
    text = str(exc).lower()
    return (
        "udapi100500" in text
        and ("maximum number" in text or "10 min" in text or "generate an otp" in text)
    ) or "too many request" in text


class UpstoxTokenManager:
    def __init__(
        self,
        config: UpstoxConfig,
        *,
        store: UpstoxTokenStore | None = None,
        refresh_fn: RefreshFn | None = None,
        cooldown: TotpCooldownGuard | None = None,
    ) -> None:
        self._config = config
        self._store = store or UpstoxTokenStore(config.token_path)
        self._refresh_fn = refresh_fn or _default_refresh(
            config.token_url,
            config.client_id,
            config.client_secret,
            config.redirect_uri,
        )
        self._cooldown = cooldown or TotpCooldownGuard(
            "upstox",
            state_path=config.cooldown_path,
        )
        self._broadcast = TokenBroadcast()
        self._memory = ""
        # Hydrate from store/env without minting
        snap = self._store.load()
        if snap and _access_token_usable(snap.access_token, snap.expires_at):
            self._memory = snap.access_token
        elif config.access_token and _access_token_usable(config.access_token):
            self._memory = config.access_token

    def register_receiver(self, receiver: Callable[[str], None]) -> Callable[[str], None]:
        """Notified with the new token whenever a mint (refresh or TOTP) succeeds."""
        return self._broadcast.register(receiver)

    def ensure_token(self, *, force_refresh: bool = False) -> str:
        """Probe-before-mint. force_refresh == broker_rejected (401)."""
        saved_refresh = ""
        if force_refresh:
            snap = self._store.load()
            saved_refresh = (snap.refresh_token if snap else "") or self._config.refresh_token
            self._memory = ""
            self._store.invalidate()
            # Do not reuse env token after broker rejection — it was just rejected
        else:
            if self._memory and _access_token_usable(self._memory):
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
            else:
                snap = self._store.load()
                if snap and _access_token_usable(snap.access_token, snap.expires_at):
                    self._memory = snap.access_token
                    # Check if stored token is about to expire
                    jwt_exp = JwtExpiry.parse_expiry_epoch(snap.access_token)
                    if jwt_exp > 0:
                        buffer = self._config.refresh_buffer_seconds
                        if jwt_exp - time.time() <= buffer:
                            force_refresh = True  # Trigger proactive refresh
                        else:
                            return snap.access_token  # Token still valid
                    else:
                        return snap.access_token  # No JWT expiry
                else:
                    env_tok = (self._config.access_token or "").strip()
                    if env_tok and _access_token_usable(env_tok):
                        exp = JwtExpiry.parse_expiry_epoch(env_tok)
                        expires_at = exp if exp > 0 else time.time() + DEFAULT_TOKEN_TTL_SECONDS
                        self._store.save(access_token=env_tok, refresh_token="", expires_at=expires_at)
                        self._memory = env_tok
                        return env_tok
                    saved_refresh = (snap.refresh_token if snap else "") or self._config.refresh_token

        refresh = saved_refresh or self._config.refresh_token
        if refresh:
            try:
                payload = self._refresh_fn(refresh)
                access = str(payload.get("access_token", ""))
                if not access:
                    raise RuntimeError("Upstox refresh returned no access_token")
                return self._persist_minted(
                    access,
                    refresh_token=str(payload.get("refresh_token") or refresh),
                    expires_in=float(payload.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS)),
                )
            except Exception:
                if not self._config.has_totp:
                    raise
        if self._config.has_totp:
            return self.generate_via_totp()
        raise RuntimeError("Upstox authenticate failed: no token/refresh/TOTP")

    def generate_via_totp(self) -> str:
        self._cooldown.check_allowed()
        self._cooldown.record_attempt()
        try:
            payload = self._totp_generate()
        except TotpRateLimitError:
            self._cooldown.record_rate_limited()
            raise
        except Exception as exc:
            if _is_upstox_otp_rate_limit(exc):
                self._cooldown.record_rate_limited()
                raise TotpRateLimitError(
                    str(exc),
                    remaining_seconds=self._cooldown.remaining_cooldown_seconds() or UPSTOX_COOLDOWN_SECONDS,
                ) from exc
            raise
        access = str(payload.get("access_token", ""))
        if not access:
            raise RuntimeError("Upstox TOTP returned no access_token")
        token = self._persist_minted(
            access,
            refresh_token=str(payload.get("refresh_token", "")),
            expires_in=float(payload.get("expires_in", 86400)),
        )
        self._cooldown.record_success()
        return token

    def _persist_minted(
        self, access: str, *, refresh_token: str, expires_in: float
    ) -> str:
        jwt_exp = JwtExpiry.parse_expiry_epoch(access)
        expires_at = jwt_exp if jwt_exp > 0 else time.time() + expires_in
        self._store.save(
            access_token=access,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        self._memory = access
        self._config.access_token = access
        self._broadcast.broadcast(access)
        return access

    def _totp_generate(self) -> dict[str, Any]:
        """Mirror src UpstoxTotpClient.generate_token response handling."""
        try:
            from pydantic import SecretStr
            from upstox_totp import UpstoxTOTP
        except ImportError as exc:
            raise RuntimeError(
                "upstox-totp required for TOTP auth — pip install upstox-totp"
            ) from exc
        client = UpstoxTOTP(
            username=self._config.mobile,
            password=SecretStr(self._config.pin),
            pin_code=SecretStr(self._config.pin),
            totp_secret=SecretStr(self._config.totp_secret),
            client_id=self._config.client_id,
            client_secret=SecretStr(self._config.client_secret),
            redirect_uri=self._config.redirect_uri,
            debug=False,
        )
        response = client.app_token.get_access_token()
        if getattr(response, "success", False) and getattr(response, "data", None):
            data = response.data
            access = getattr(data, "access_token", None) or (
                data.get("access_token") if isinstance(data, dict) else None
            )
            if not access:
                raise RuntimeError(f"Upstox TOTP response missing access_token: {response!r}")
            refresh = getattr(data, "refresh_token", "") or ""
            if isinstance(data, dict):
                refresh = data.get("refresh_token", "") or ""
            return {"access_token": access, "refresh_token": refresh, "expires_in": 86400}

        err = getattr(response, "error", None) or response
        err_msg = _response_error_message(err) or "TOTP token generation failed"
        if _is_upstox_otp_rate_limit(err_msg):
            raise TotpRateLimitError(err_msg)
        raise RuntimeError(err_msg)

    def current(self) -> str:
        if self._memory:
            return self._memory
        snap = self._store.load()
        return snap.access_token if snap else self._config.access_token

    def is_expiring_soon(self, *, within: float | None = None) -> bool:
        """True when the current token will exceed the refresh buffer soon.

        Lets the app warn before a mid-session expiry instead of
        only finding out on the next 401. Mirrors the proactive-refresh
        check inside ensure_token().
        """
        import time

        token = self.current()
        if not token:
            return True  # no token -> needs (re)mint now
        jwt_exp = JwtExpiry.parse_expiry_epoch(token)
        if jwt_exp <= 0:
            # No JWT expiry (static token) — trust until broker rejects.
            return False
        buffer = self._config.refresh_buffer_seconds if within is None else within
        return jwt_exp - time.time() <= buffer

    def token_status(self) -> dict[str, object]:
        """Health snapshot for mass_status() / a liveness probe."""
        token = self.current()
        jwt_exp = JwtExpiry.parse_expiry_epoch(token) if token else -1.0
        return {
            "has_token": bool(token),
            "expires_at": jwt_exp if jwt_exp > 0 else None,
            "expiring_soon": self.is_expiring_soon(),
        }


def _response_error_message(error: Any) -> str:
    if not error:
        return ""
    if isinstance(error, dict):
        parts = [
            str(error.get("message") or ""),
            str(error.get("code") or error.get("errorCode") or ""),
        ]
        return " ".join(part for part in parts if part)
    return str(error)
