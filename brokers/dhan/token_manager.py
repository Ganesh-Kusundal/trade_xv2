"""Token Management Utilities for Dhan broker.

Provides TOTP token generation, env file updates, and secret reading
utilities used by the Dhan broker factory and token scheduler.

All functions are pure utilities with no global state, making them
easily testable and reusable.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from brokers.dhan.settings import DhanConnectionSettings

logger = logging.getLogger(__name__)


def generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP.
    
    Uses secrets from settings if provided, otherwise falls back to
    environment variables DHAN_PIN / DHAN_TOTP_SECRET.
    
    Args:
        settings: Dhan connection settings (optional). If not provided,
                  reads from environment variables.
    
    Returns:
        Fresh access token string, or None if generation fails.
    """
    if settings and settings.has_totp:
        pin = settings.pin
        totp_secret = settings.totp_secret
        token_url = settings.generate_token_url
    else:
        pin = read_secret("DHAN_PIN", "DHAN_PIN_FILE")
        totp_secret = read_secret("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")
        from brokers.dhan.settings import _GENERATE_TOKEN_URL
        token_url = _GENERATE_TOKEN_URL
    
    if not pin or not totp_secret:
        return None
    
    try:
        import pyotp
        import requests as _requests
        
        totp_code = pyotp.TOTP(totp_secret).now()
        client_id = settings.client_id if settings else os.environ.get("DHAN_CLIENT_ID", "")
        params = {"dhanClientId": client_id, "pin": pin, "totp": totp_code}
        url = f"{token_url}?{urlencode(params)}"
        resp = _requests.post(url, timeout=15)
        
        if resp.status_code != 200:
            logger.warning("TOTP token generation failed: HTTP %d", resp.status_code)
            return None
        
        body = resp.json()
        data = body.get("data", body)
        result: str = data.get("accessToken") or data.get("access_token") or ""
        return result or None
        
    except Exception as exc:
        logger.warning("TOTP token generation failed: %s", exc)
        return None


def read_secret(env_key: str, file_key: str) -> str | None:
    """Read a secret from environment variable or file.
    
    Tries the environment variable first, then falls back to reading
    from a file path specified in another environment variable.
    
    Args:
        env_key: Environment variable name for the secret value
        file_key: Environment variable name for the file path
    
    Returns:
        Secret value if found, None otherwise.
    """
    val = os.environ.get(env_key, "")
    if val:
        return val
    
    file_path = os.environ.get(file_key, "")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    
    return None


def update_env_token(env_path: Path, token: str) -> None:
    """Update DHAN_ACCESS_TOKEN in the env file atomically.
    
    Uses fcntl.flock for cross-process exclusion and a temp-file +
    os.replace so readers never see a partially-written file. If the
    token key is missing, it is appended while preserving all other keys,
    comments, and blank lines.
    
    Args:
        env_path: Path to the .env file to update
        token: New access token value
    """
    if not env_path.exists():
        return
    
    try:
        import fcntl
    except Exception as exc:  # pragma: no cover - non-Unix fallback
        logger.warning("fcntl unavailable, env update unprotected: %s", exc)
        return
    
    fd: int | None = None
    tmp_path = env_path.with_suffix(f"{env_path.suffix}.tmp")
    
    try:
        # Hold an exclusive lock on the env file while we read and replace it.
        fd = os.open(str(env_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            content = fh.read()
        
        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("DHAN_ACCESS_TOKEN="):
                lines[i] = f"DHAN_ACCESS_TOKEN={token}"
                updated = True
                break
        
        if not updated:
            # Preserve a trailing blank line when appending if the file ends
            # without a newline; otherwise just append the new key.
            if lines and not content.endswith("\n"):
                lines.append("")
            lines.append(f"DHAN_ACCESS_TOKEN={token}")
        
        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"
        
        tmp_path.write_text(new_content, encoding="utf-8")
        
        # fsync temp file contents before the atomic rename.
        with open(tmp_path, "rb") as tmp_fh:
            os.fsync(tmp_fh.fileno())
        
        # fsync the directory so the rename is durable.
        dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        
        os.replace(tmp_path, env_path)
        
    except PermissionError:
        # Env file is read-only (e.g. credentials managed externally). Persist
        # the new token via the JsonTokenStateStore instead and continue.
        logger.info("Env file is read-only; token persisted to state store only.")
    except Exception as exc:
        logger.warning("Failed to update env token: %s", exc)
        if tmp_path.exists():
            tmp_path.unlink()
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception as exc:
                logger.debug("file_unlock_failed: %s", exc)
            try:
                os.close(fd)
            except Exception as exc:
                logger.debug("file_close_failed: %s", exc)
