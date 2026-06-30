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
    for key, value in _read_env_file(path).items():
        os.environ[key] = value


def _read_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


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


def _upstox_totp_from_env(env: dict[str, str]) -> AuthGate | None:
    """Return AuthGate when *env* has complete TOTP config, else None."""
    client_id = env.get("UPSTOX_CLIENT_ID", "").strip() or env.get("UPSTOX_API_KEY", "").strip()
    auth_mode = env.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
    mobile = env.get("UPSTOX_MOBILE", "").strip()
    pin = env.get("UPSTOX_PIN", "").strip()
    if not pin:
        file_path = env.get("UPSTOX_PIN_FILE", "").strip()
        if file_path and Path(file_path).exists():
            pin = Path(file_path).read_text().strip()
    totp_secret = env.get("UPSTOX_TOTP_SECRET", "").strip()
    if not totp_secret:
        file_path = env.get("UPSTOX_TOTP_SECRET_FILE", "").strip()
        if file_path and Path(file_path).exists():
            totp_secret = Path(file_path).read_text().strip()
    client_secret = env.get("UPSTOX_CLIENT_SECRET", "").strip()

    if not client_id:
        return None
    if auth_mode != "TOTP":
        return None
    if not mobile or not pin or not totp_secret:
        return None
    if not client_secret:
        return None
    return AuthGate(True, None)


def upstox_totp_gate() -> AuthGate:
    """True when Upstox TOTP credentials are present (.env.upstox or .env.local)."""
    last_reason = ".env.upstox and .env.local missing or empty"
    for name in (".env.upstox", ".env.local"):
        env_path = REPO_ROOT / name
        if not env_path.exists() or env_path.stat().st_size == 0:
            continue
        env = _read_env_file(env_path)
        client_id = env.get("UPSTOX_CLIENT_ID", "").strip() or env.get("UPSTOX_API_KEY", "").strip()
        auth_mode = env.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
        if not client_id:
            last_reason = f"{name}: UPSTOX_CLIENT_ID / UPSTOX_API_KEY not set"
            continue
        if auth_mode != "TOTP":
            last_reason = f"{name}: UPSTOX_AUTH_MODE={auth_mode} (need TOTP)"
            continue
        gate = _upstox_totp_from_env(env)
        if gate is not None:
            return AuthGate(True, env_path)
        last_reason = f"{name}: UPSTOX TOTP fields incomplete"
        client_secret = env.get("UPSTOX_CLIENT_SECRET", "").strip()
        if not client_secret:
            last_reason = f"{name}: UPSTOX_CLIENT_SECRET not set"
    return AuthGate(False, None, last_reason)


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
