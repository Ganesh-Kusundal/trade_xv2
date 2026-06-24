"""Token Management Utilities for Dhan broker.

Provides TOTP token generation, env file updates, and secret reading
utilities used by the Dhan broker factory and token scheduler.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.dhan.settings import DhanConnectionSettings

logger = logging.getLogger(__name__)


def generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP (delegates to DhanTotpClient)."""
    from brokers.dhan.totp_client import DhanTotpClient

    return DhanTotpClient(settings).generate()


def read_secret(env_key: str, file_key: str) -> str | None:
    """Read a secret from environment variable or file."""
    val = os.environ.get(env_key, "")
    if val:
        return val

    file_path = os.environ.get(file_key, "")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()

    return None


def update_env_token(env_path: Path, token: str) -> None:
    """Update DHAN_ACCESS_TOKEN in the env file atomically."""
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
            if lines and not content.endswith("\n"):
                lines.append("")
            lines.append(f"DHAN_ACCESS_TOKEN={token}")

        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"

        tmp_path.write_text(new_content, encoding="utf-8")

        with open(tmp_path, "rb") as tmp_fh:
            os.fsync(tmp_fh.fileno())

        dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, env_path)

    except PermissionError:
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


# Backward-compatible alias used by existing imports
_update_env_token = update_env_token
