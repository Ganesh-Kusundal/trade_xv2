"""Credential gates for live auth / TOTP integration tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AuthGate:
    """Whether live auth tests can run for a broker."""

    configured: bool
    env_path: Path | None
    reason: str = ""


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _env_or_file(key: str, file_key: str) -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    file_path = os.environ.get(file_key, "").strip()
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return ""


def dhan_totp_gate() -> AuthGate:
    """True when Dhan TOTP credentials are present for live token generation."""
    env_path = REPO_ROOT / ".env.local"
    if not env_path.exists() or env_path.stat().st_size == 0:
        return AuthGate(False, None, ".env.local missing or empty")

    _load_env_file(env_path)
    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    pin = _env_or_file("DHAN_PIN", "DHAN_PIN_FILE")
    totp_secret = _env_or_file("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")

    if not client_id:
        return AuthGate(False, env_path, "DHAN_CLIENT_ID not set")
    if not pin or not totp_secret:
        return AuthGate(False, env_path, "DHAN_PIN / DHAN_TOTP_SECRET not configured")
    return AuthGate(True, env_path)


def upstox_totp_gate() -> AuthGate:
    """True when Upstox TOTP credentials are present for live token generation."""
    env_path = REPO_ROOT / ".env.upstox"
    if not env_path.exists() or env_path.stat().st_size == 0:
        return AuthGate(False, None, ".env.upstox missing or empty")

    _load_env_file(env_path)
    client_id = (
        os.environ.get("UPSTOX_CLIENT_ID", "").strip()
        or os.environ.get("UPSTOX_API_KEY", "").strip()
    )
    auth_mode = os.environ.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
    mobile = os.environ.get("UPSTOX_MOBILE", "").strip()
    pin = _env_or_file("UPSTOX_PIN", "UPSTOX_PIN_FILE")
    totp_secret = _env_or_file("UPSTOX_TOTP_SECRET", "UPSTOX_TOTP_SECRET_FILE")

    if not client_id:
        return AuthGate(False, env_path, "UPSTOX_CLIENT_ID / UPSTOX_API_KEY not set")
    if auth_mode != "TOTP":
        return AuthGate(False, env_path, f"UPSTOX_AUTH_MODE={auth_mode} (need TOTP)")
    if not mobile or not pin or not totp_secret:
        return AuthGate(False, env_path, "UPSTOX TOTP fields incomplete")
    return AuthGate(True, env_path)


def dhan_readonly_gate() -> AuthGate:
    """True when a valid Dhan access token is present (no TOTP required)."""
    env_path = REPO_ROOT / ".env.local"
    if not env_path.exists():
        return AuthGate(False, None, ".env.local missing")
    _load_env_file(env_path)
    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
    if client_id and token:
        return AuthGate(True, env_path)
    return AuthGate(False, env_path, "DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN missing")
