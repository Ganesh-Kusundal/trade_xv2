"""Secrets manager — unified access to credentials from env and files.

Moved from root-level ``secrets_manager.py`` to ``infrastructure/secrets/``
to respect architectural layering. Brokers and application code should
import from here rather than the root-level orphan.

Usage::

    from infrastructure.secrets import SecretsManager

    mgr = SecretsManager()
    totp = mgr.get_dhan_totp_secret()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class SecretsManager:
    """Read secrets from environment variables or gitignored files.

    Supports the file-based layout documented in ``config/CONFIG.md`` and
    provides a single interface that can be extended to Vault/AWS SM later.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()

    def get_env(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)

    def get_file(self, relative_path: str, *, strip: bool = True) -> str:
        path = self._root / relative_path
        if not path.exists():
            return ""
        value = path.read_text(encoding="utf-8")
        return value.strip() if strip else value

    def get_dhan_totp_secret(self) -> str:
        """Get Dhan TOTP secret from env var."""
        return self.get_env("DHAN_TOTP_SECRET")

    def get_dhan_pin(self) -> str:
        """Get Dhan PIN from env var."""
        return self.get_env("DHAN_PIN")

    def get_upstox_pin(self) -> str:
        """Get Upstox PIN from env var."""
        return self.get_env("UPSTOX_PIN")

    def get_upstox_totp_secret(self) -> str:
        """Get Upstox TOTP secret from env var."""
        return self.get_env("UPSTOX_TOTP_SECRET")

    def get_api_key(self) -> str:
        return self.get_env("API_KEY")

    def require(self, key: str) -> str:
        value = self.get_env(key)
        if not value:
            raise ValueError(f"Required secret {key} is not set")
        return value


__all__ = ["SecretsManager"]
