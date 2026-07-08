"""Encrypted token state store.

Wraps :class:`JsonTokenStateStore` so OAuth tokens are persisted
encrypted-at-rest (Fernet) instead of plaintext.  This closes the
CWE-312 sensitive-data-in-cleartext gap: the previous store wrote
``access_token`` / ``refresh_token`` as readable JSON.

Backward compatibility: on load, an encrypted payload is decrypted;
if decryption fails (legacy plaintext file) the raw JSON is used, so
existing unencrypted token files still load.  When no
``SECRET_ENCRYPTION_KEY`` is configured, behaviour degrades to the
plaintext store with a warning (same as before) rather than failing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from infrastructure.security.secret_manager import SecretManager

from .json_token_state_store import JsonTokenStateStore

logger = logging.getLogger(__name__)

_ENCRYPTED_MARKER = "enc:v1:"


class EncryptedTokenStateStore:
    """JSON token store that encrypts the persisted payload with Fernet."""

    def __init__(self, path: Path, *, secret_manager: SecretManager | None = None) -> None:
        self._inner = JsonTokenStateStore(path)
        self._secrets = secret_manager or SecretManager.get_instance()

    @property
    def path(self) -> Path:
        return self._inner.path

    def load(self) -> dict | None:
        raw = self._inner.load()
        if raw is None:
            return None
        # Legacy plaintext payloads are plain dicts from json.load().
        if not isinstance(raw, dict) or "access_token" in raw:
            return raw
        # Encrypted payload: a single ``ciphertext`` key.
        ciphertext = raw.get("ciphertext")
        if not ciphertext:
            return raw
        try:
            plaintext = self._secrets.decrypt(ciphertext)
            return json.loads(plaintext)
        except Exception as exc:  # noqa: BLE001 - fall back to plaintext on failure
            logger.warning("Token decryption failed, using stored payload: %s", exc)
            return raw

    def save(self, state: dict) -> None:
        if not self._secrets.is_encryption_enabled:
            logger.warning(
                "SECRET_ENCRYPTION_KEY not set — persisting Upstox token state unencrypted"
            )
            self._inner.save(state)
            return
        ciphertext = self._secrets.encrypt(json.dumps(state))
        self._inner.save({"ciphertext": ciphertext})

    def clear(self) -> None:
        self._inner.clear()
