"""Process-wide TOTP rate-limit guard — mirror src/infrastructure/auth/totp_cooldown.

Broker login APIs enforce OTP/TOTP lockouts. This guard keeps local processes
from hammering those endpoints across restarts. No sleeps/polling — callers
raise TotpRateLimitError with remaining seconds and stop.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import ClassVar

from plugins.brokers.common.constants import DHAN_COOLDOWN_SECONDS, UPSTOX_COOLDOWN_SECONDS

DEFAULT_COOLDOWN_SECONDS = DHAN_COOLDOWN_SECONDS
BROKER_COOLDOWN_SECONDS: dict[str, float] = {
    "dhan": DHAN_COOLDOWN_SECONDS,
    "upstox": UPSTOX_COOLDOWN_SECONDS,
}

# v2/.../common/totp_cooldown.py → parents[5] = repo root (shared with src runtime/)
_REPO_ROOT = Path(__file__).resolve().parents[5]


class TotpRateLimitError(RuntimeError):
    """Raised when TOTP generation is blocked by local or broker cooldown."""

    def __init__(self, message: str, *, remaining_seconds: float = 0.0) -> None:
        super().__init__(message)
        self.remaining_seconds = remaining_seconds


class TotpCooldownGuard:
    """Shared cooldown tracker for TOTP token generation attempts."""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _instances: ClassVar[dict[str, TotpCooldownGuard]] = {}

    def __init__(
        self,
        broker: str,
        cooldown_seconds: float | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._broker = broker.lower()
        self._cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else BROKER_COOLDOWN_SECONDS.get(self._broker, DEFAULT_COOLDOWN_SECONDS)
        )
        self._state_path = (
            state_path or _REPO_ROOT / "runtime" / f"{self._broker}-totp-cooldown.json"
        )
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._load_state()

    @classmethod
    def for_broker(cls, broker: str, cooldown_seconds: float | None = None) -> TotpCooldownGuard:
        key = broker.lower()
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(key, cooldown_seconds=cooldown_seconds)
            return cls._instances[key]

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text())
            self._last_attempt_at = _coerce_wall_clock(data.get("last_attempt_at"))
            self._last_success_at = _coerce_wall_clock(data.get("last_success_at"))
            # legacy v2 field — treat as attempt timestamp
            if self._last_attempt_at is None:
                self._last_attempt_at = _coerce_wall_clock(data.get("rate_limited_at"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return

    def _persist_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(
                {
                    "broker": self._broker,
                    "last_attempt_at": self._last_attempt_at,
                    "last_success_at": self._last_success_at,
                },
                indent=2,
            )
        )

    def remaining_cooldown_seconds(self) -> float:
        if self._last_attempt_at is None:
            return 0.0
        elapsed = time.time() - self._last_attempt_at
        return max(0.0, self._cooldown_seconds - elapsed)

    def check_allowed(self) -> None:
        remaining = self.remaining_cooldown_seconds()
        if remaining > 0:
            raise TotpRateLimitError(
                f"{self._broker} TOTP cooldown active; retry in {remaining:.0f}s",
                remaining_seconds=remaining,
            )

    def record_attempt(self) -> None:
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()

    def record_success(self) -> None:
        with self._lock:
            now = time.time()
            self._last_attempt_at = now
            self._last_success_at = now
            self._persist_state()

    def record_rate_limited(self) -> None:
        """Broker-side rate limit — enforce full cooldown from now."""
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()


def _coerce_wall_clock(value: object) -> float | None:
    try:
        ts = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    # Ignore old monotonic timestamps (meaningless after restart)
    if ts < 1_000_000_000:
        return None
    return ts
