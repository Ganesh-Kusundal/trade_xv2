"""Dhan authentication — TOTP token generation and renewal.

Maps to Trade_J's ``DhanAuthClient`` and ``DhanTokenManager``:

- ``DhanAuthClient`` — HTTP calls to Dhan's auth endpoints
- ``DhanTokenState`` / ``DhanTokenInfo`` — typed token state
- ``DhanAuthRejected`` / ``DhanHttpError`` — auth-specific errors
- ``DhanTokenManager`` — full token lifecycle (TOTP, WEB_RENEWABLE, STATIC)
- ``read_secret_file`` — PIN/TOTP secret file reader
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode

import requests

from brokers.common.core.auth import TotpGenerator
from brokers.dhan.mapper.mapping import first_present, string_value

# ── Token state dataclasses ─────────────────────────────────────────


@dataclass(frozen=True)
class DhanTokenState:
    """Immutable snapshot of a Dhan access token."""

    access_token: str
    expiry_epoch_ms: int
    issued_at_epoch_ms: int
    source: str  # STATIC, TOTP_GENERATED, WEB_RENEWABLE, BOOTSTRAP


@dataclass
class DhanTokenInfo:
    """Token validity info from the profile endpoint."""

    valid: bool
    expiry_epoch_ms: int
    refresh_recommended: bool


# ── Auth HTTP client ─────────────────────────────────────────────────


GENERATE_TOKEN_ENDPOINT = "https://auth.dhan.co/app/generateAccessToken"
RENEW_TOKEN_ENDPOINT = "https://api.dhan.co/v2/RenewToken"
PROFILE_ENDPOINT = "https://api.dhan.co/v2/profile"


class DhanAuthClient:
    """HTTP client for Dhan authentication endpoints.

    Endpoints:
    - ``generateAccessToken``  TOTP → fresh token
    - ``RenewToken``           Renew valid token (WEB_RENEWABLE)
    - ``profile``              Validate token + read expiry
    """

    def __init__(self, timeout_seconds: int = 15) -> None:
        self._timeout = timeout_seconds
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def generate_via_totp(self, client_id: str, pin: str, totp: str) -> DhanTokenState:
        """Generate a fresh access token via TOTP.

        :raises DhanAuthRejected: if Dhan rejects the credentials.
        :raises DhanHttpError: if the HTTP request itself fails.
        """
        params = {
            "dhanClientId": client_id,
            "pin": pin,
            "totp": totp,
        }
        url = f"{GENERATE_TOKEN_ENDPOINT}?{urlencode(params)}"
        response = self._session.post(url, timeout=self._timeout)

        if response.status_code != 200:
            raise DhanHttpError(
                f"Token generation failed: HTTP {response.status_code}",
                response.status_code,
            )
        body = response.json()
        self._verify_business_success(body, "generate token")
        return self._map_token_state(body, "TOTP_GENERATED")

    def renew_token(self, client_id: str, access_token: str) -> DhanTokenState:
        """Renew an existing access token (WEB_RENEWABLE mode)."""
        response = self._session.post(
            RENEW_TOKEN_ENDPOINT,
            headers={
                "access-token": access_token,
                "dhanClientId": client_id,
            },
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise DhanHttpError(
                f"Token renewal failed: HTTP {response.status_code}",
                response.status_code,
            )
        body = response.json()
        self._verify_business_success(body, "renew token")
        return self._map_token_state(body, "WEB_RENEWABLE")

    def fetch_profile(self, access_token: str, refresh_buffer_ms: int = 600_000) -> DhanTokenInfo:
        """Validate token and return validity + expiry info.

        :param refresh_buffer_ms: notify `refresh_recommended` when token
            expires within this many milliseconds.
        """
        response = self._session.get(
            PROFILE_ENDPOINT,
            headers={"access-token": access_token},
            timeout=self._timeout,
        )
        if response.status_code != 200:
            raise DhanHttpError(
                f"Profile fetch failed: HTTP {response.status_code}",
                response.status_code,
            )
        body = response.json()
        token_validity = body.get("tokenValidity", "")
        if not token_validity:
            raise ValueError("Dhan profile response missing tokenValidity")

        india_tz = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
        expiry_dt = datetime.strptime(token_validity, "%d/%m/%Y %H:%M")
        expiry_dt = expiry_dt.replace(tzinfo=india_tz)
        expiry_epoch_ms = int(expiry_dt.timestamp() * 1000)

        now_ms = int(datetime.now().timestamp() * 1000)
        valid = expiry_epoch_ms > now_ms
        refresh_recommended = expiry_epoch_ms <= now_ms + refresh_buffer_ms
        return DhanTokenInfo(
            valid=valid,
            expiry_epoch_ms=expiry_epoch_ms,
            refresh_recommended=refresh_recommended,
        )

    # ── Private helpers ─────────────────────────────────────────────

    def _map_token_state(self, body: dict, source: str) -> DhanTokenState:
        data = body.get("data", body)
        access_token = string_value(first_present(data, "accessToken", "access_token"))
        expiry_time = string_value(first_present(data, "expiryTime", "expiry_time"))
        if not access_token or not expiry_time:
            raise ValueError("Dhan auth response missing accessToken or expiryTime")

        india_tz = __import__("zoneinfo").ZoneInfo("Asia/Kolkata")
        expiry_dt = datetime.fromisoformat(expiry_time)
        if expiry_dt.tzinfo is None:
            expiry_dt = expiry_dt.replace(tzinfo=india_tz)
        expiry_epoch_ms = int(expiry_dt.timestamp() * 1000)
        issued_at_ms = int(datetime.now().timestamp() * 1000)

        return DhanTokenState(
            access_token=access_token,
            expiry_epoch_ms=expiry_epoch_ms,
            issued_at_epoch_ms=issued_at_ms,
            source=source,
        )

    def _verify_business_success(self, body: dict, action: str) -> None:
        status = body.get("status", "")
        if status and status.lower() == "error":
            message = body.get("message", "unknown error")
            rate_limited = "2 minutes" in message.lower() or "once every" in message.lower()
            raise DhanAuthRejected(f"Dhan {action} rejected: {message}", rate_limited)


# ── Auth error types ─────────────────────────────────────────────────


class DhanAuthRejected(Exception):
    """Dhan rejected the authentication attempt."""

    def __init__(self, message: str, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited


class DhanHttpError(Exception):
    """HTTP-level error from a Dhan auth call."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@runtime_checkable
class DhanTokenProvider(Protocol):
    """Token source for authenticated REST calls (Trade_J ``DhanTokenProvider``)."""

    def ensure_valid_and_get(self) -> str:
        """Atomically ensure validity and return the current access token."""
        ...

    def invalidate(self) -> None:
        """Drop the cached token so the next call mints or adopts a fresh one."""
        ...

    def token_generation_id(self) -> int:
        """Monotonic counter bumped on every new token acquisition."""
        ...

    def invalidate_generation(self, failed_generation_id: int) -> bool:
        """CAS invalidation — only clear if generation still matches."""
        ...


# ── Token lifecycle manager ──────────────────────────────────────────


class DhanTokenManager:
    """Manages token lifecycle: STATIC, TOTP_GENERATED, WEB_RENEWABLE.

    Responsibilities:
    - Reuse an existing valid token (no premature renewal)
    - Adopt a bootstrap token passed at startup (WEB_RENEWABLE)
    - Confirm existing tokens via the profile endpoint before expiry
    - Generate fresh tokens when needed (TOTP or renewal)
    - Persist state to disk after every acquisition

    Design: Trade_J ``DhanTokenManager``.
    """

    TOKEN_ACQUISITION_COOLDOWN_MS = 130_000  # ~2 min 10 s
    CLOCK_SKEW_TOLERANCE_MS = 30_000  # 30 s

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        auth_mode: str = "STATIC",
        token_state_file: Path | None = None,
        refresh_buffer_minutes: int = 10,
    ) -> None:
        self._client_id = client_id
        self._access_token = access_token
        self._pin = pin
        self._totp_secret = totp_secret
        self._auth_mode = auth_mode
        self._token_state_file = token_state_file
        self._refresh_buffer_ms = refresh_buffer_minutes * 60_000

        self._auth_client = DhanAuthClient()
        self._generator = TotpGenerator()
        self._current_state: DhanTokenState | None = None
        self._last_acquisition_attempt_ms: int = 0
        self._refresh_lock = threading.RLock()
        self._token_generation_id: int = 0

        if token_state_file and token_state_file.exists():
            self._load_state()

    @property
    def auth_mode(self) -> str:
        return self._auth_mode

    def get_access_token(self) -> str:
        """Return the current access token, triggering refresh if needed."""
        return self.ensure_valid_and_get()

    def ensure_valid_and_get(self) -> str:
        """Atomically ensure validity and return the access token.

        Maps to Trade_J's ``DhanTokenManager.ensureValidAndGet()``.
        """
        if self._auth_mode == "STATIC":
            if not self._access_token:
                raise ValueError("Dhan access token not configured")
            return self._access_token

        with self._refresh_lock:
            self._ensure_valid_locked()
            if not self._current_state or not self._current_state.access_token:
                raise ValueError("Dhan token manager did not resolve an access token")
            return self._current_state.access_token

    def ensure_valid(self) -> None:
        """Ensure current token is valid, refreshing only when necessary.

        Maps to Trade_J's ``DhanTokenManager.ensureValid()``.
        """
        if self._auth_mode == "STATIC":
            return
        with self._refresh_lock:
            self._ensure_valid_locked()

    def _ensure_valid_locked(self) -> None:
        import time

        now_ms = int(time.time() * 1000)
        if self._is_reusable(self._current_state, now_ms):
            return
        self._current_state = self._resolve_valid_state(now_ms)
        if not self._current_state:
            raise ValueError("Unable to resolve a valid Dhan access token")

    def token_generation_id(self) -> int:
        return self._token_generation_id

    def invalidate(self) -> None:
        """Invalidate current token; next call to :meth:`get_access_token` regenerates."""
        with self._refresh_lock:
            self._current_state = None
            self._token_generation_id += 1
            self._save_state(None)

    def invalidate_generation(self, failed_generation_id: int) -> bool:
        """CAS invalidation used after broker auth rejection (Trade_J 806 path)."""
        with self._refresh_lock:
            if self._token_generation_id != failed_generation_id:
                return False
            self._current_state = None
            self._token_generation_id += 1
            self._save_state(None)
            return True

    def current_snapshot(self) -> DhanTokenState | None:
        """Return cached token state without forcing a mint."""
        return self._current_state

    def update_cached_expiry(self, broker_expiry_epoch_ms: int) -> bool:
        """Sync cached expiry from broker profile without re-minting."""
        with self._refresh_lock:
            state = self._current_state
            if not state or not state.access_token:
                return False
            if broker_expiry_epoch_ms == state.expiry_epoch_ms:
                return True
            updated = DhanTokenState(
                access_token=state.access_token,
                expiry_epoch_ms=broker_expiry_epoch_ms,
                issued_at_epoch_ms=state.issued_at_epoch_ms,
                source=state.source,
            )
            self._current_state = updated
            self._save_state(updated)
            return True

    def validate_persisted_token_at_startup(self) -> None:
        """Profile-check persisted token before serving API calls.

        Catches the case where ``expiry_epoch_ms`` in the state file is still
        in the future but Dhan has already revoked the token.
        """
        if self._auth_mode == "STATIC":
            return
        with self._refresh_lock:
            state = self._current_state
            if not state or not state.access_token:
                return
            try:
                info = self._auth_client.fetch_profile(state.access_token, self._refresh_buffer_ms)
                if info.valid and not info.refresh_recommended:
                    self._current_state = DhanTokenState(
                        access_token=state.access_token,
                        expiry_epoch_ms=info.expiry_epoch_ms,
                        issued_at_epoch_ms=state.issued_at_epoch_ms,
                        source=state.source,
                    )
                    self._save_state(self._current_state)
                    return
                if info.valid:
                    updated = DhanTokenState(
                        access_token=state.access_token,
                        expiry_epoch_ms=info.expiry_epoch_ms,
                        issued_at_epoch_ms=state.issued_at_epoch_ms,
                        source=state.source,
                    )
                    self._current_state = updated
                    self._save_state(updated)
                    return
                self._current_state = None
                self._token_generation_id += 1
                self._save_state(None)
            except DhanHttpError as exc:
                if exc.status_code in {400, 401}:
                    self._current_state = None
                    self._token_generation_id += 1
                    self._save_state(None)
            except Exception:
                return

    # ── State resolution ─────────────────────────────────────────────

    def _resolve_valid_state(self, now_ms: int) -> DhanTokenState | None:
        if self._current_state and self._current_state.access_token:
            confirmed = self._confirm_existing_state(self._current_state, now_ms)
            if confirmed:
                return self._persist(confirmed)

        adopted = self._adopt_bootstrap_token(now_ms)
        if adopted:
            return self._persist(adopted)

        # Generate a fresh token since the current one is expired/invalid/needs refresh
        try:
            return self._persist(self._generate_fresh_token(now_ms))
        except DhanAuthRejected as exc:
            if exc.rate_limited:
                adopted_after_cooldown = self._adopt_bootstrap_token(now_ms)
                if adopted_after_cooldown:
                    return self._persist(adopted_after_cooldown)
            raise
        except Exception as exc:
            # If generating a fresh token fails, but the current token is still valid (not fully expired),
            # fallback to using it for now rather than failing.
            if (
                self._current_state
                and self._current_state.access_token
                and self._current_state.expiry_epoch_ms > now_ms
            ):
                return self._current_state
            raise exc

    def _confirm_existing_state(self, state: DhanTokenState, now_ms: int) -> DhanTokenState | None:
        if not state.access_token:
            return None
        if self._is_reusable(state, now_ms):
            return state
        if state.expiry_epoch_ms > now_ms:
            try:
                info = self._auth_client.fetch_profile(state.access_token, self._refresh_buffer_ms)
                if info.valid and not info.refresh_recommended:
                    return DhanTokenState(
                        access_token=state.access_token,
                        expiry_epoch_ms=info.expiry_epoch_ms,
                        issued_at_epoch_ms=state.issued_at_epoch_ms,
                        source=state.source,
                    )
            except Exception:
                return None
        return None

    def _adopt_bootstrap_token(self, now_ms: int) -> DhanTokenState | None:
        """Adopt the bootstrap (pre-configured) token if valid.

        Matches Trade_J's bootstrap adoption: if the caller supplied a
        static token and it validates against the profile, use it as-is
        without going through TOTP/renewal.
        """
        if not self._access_token:
            return None
        if self._current_state and self._access_token == self._current_state.access_token:
            return None
        try:
            info = self._auth_client.fetch_profile(self._access_token, self._refresh_buffer_ms)
            if not info.valid:
                return None
            return DhanTokenState(
                access_token=self._access_token,
                expiry_epoch_ms=info.expiry_epoch_ms,
                issued_at_epoch_ms=now_ms,
                source="BOOTSTRAP",
            )
        except Exception:
            return None

    def _generate_fresh_token(self, now_ms: int) -> DhanTokenState:
        if (
            self._last_acquisition_attempt_ms > 0
            and now_ms - self._last_acquisition_attempt_ms < self.TOKEN_ACQUISITION_COOLDOWN_MS
        ):
            remaining_s = (
                self.TOKEN_ACQUISITION_COOLDOWN_MS - (now_ms - self._last_acquisition_attempt_ms)
            ) // 1000
            raise DhanAuthRejected(
                f"Dhan token generation cooldown active; retry after {remaining_s}s",
                rate_limited=True,
            )

        self._last_acquisition_attempt_ms = now_ms

        if self._auth_mode == "TOTP_GENERATED":
            if not self._pin or not self._totp_secret:
                raise ValueError("pin and totp_secret required for TOTP mode")
            totp_code = self._generator.current_code(self._totp_secret)
            return self._auth_client.generate_via_totp(self._client_id, self._pin, totp_code)

        if self._auth_mode == "WEB_RENEWABLE":
            if not self._current_state or not self._current_state.access_token:
                raise ValueError("Cannot renew without an active token")
            return self._auth_client.renew_token(self._client_id, self._current_state.access_token)

        raise ValueError(f"Unknown auth mode: {self._auth_mode}")

    def _is_reusable(self, state: DhanTokenState | None, now_ms: int) -> bool:
        if not state or not state.access_token:
            return False
        return (
            state.expiry_epoch_ms > now_ms + self._refresh_buffer_ms + self.CLOCK_SKEW_TOLERANCE_MS
        )

    def _persist(self, state: DhanTokenState) -> DhanTokenState:
        previous = self._current_state.access_token if self._current_state else None
        if state.access_token != previous:
            self._token_generation_id += 1
        self._save_state(state)
        return state

    # ── State persistence ────────────────────────────────────────────

    def _save_state(self, state: DhanTokenState | None) -> None:
        if not self._token_state_file:
            return
        if state is None:
            self._token_state_file.unlink(missing_ok=True)
            return
        self._token_state_file.parent.mkdir(parents=True, exist_ok=True)
        self._token_state_file.parent.chmod(0o700)
        data = {
            "access_token": state.access_token,
            "expiry_epoch_ms": state.expiry_epoch_ms,
            "issued_at_epoch_ms": state.issued_at_epoch_ms,
            "source": state.source,
        }
        self._token_state_file.write_text(json.dumps(data, indent=2))
        self._token_state_file.chmod(0o600)

    def _load_state(self) -> None:
        if not self._token_state_file or not self._token_state_file.exists():
            return
        try:
            data = json.loads(self._token_state_file.read_text())
            self._current_state = DhanTokenState(
                access_token=data.get("access_token", ""),
                expiry_epoch_ms=data.get("expiry_epoch_ms", 0),
                issued_at_epoch_ms=data.get("issued_at_epoch_ms", 0),
                source=data.get("source", ""),
            )
        except (json.JSONDecodeError, KeyError):
            self._current_state = None


# ── Secret file helpers ───────────────────────────────────────────────


def read_secret_file(path: Path | None, label: str) -> str:
    """Read a secret (PIN or TOTP) from a file.

    :param path: File path to read.
    :param label: Human-friendly label for error messages.
    :returns: Stripped file contents.
    :raises ValueError: if ``path`` is ``None``, does not exist, or is empty.
    """
    if path is None:
        raise ValueError(f"Dhan {label} file is not configured")
    if not path.exists():
        raise ValueError(f"Dhan {label} file not found at {path}")
    value = path.read_text().strip()
    if not value:
        raise ValueError(f"Dhan {label} file is empty at {path}")
    return value
