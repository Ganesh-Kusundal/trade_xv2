"""Parse JWT ``exp`` claim without signature verification."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone


class JwtExpiry:
    """Shared JWT expiry parsing for broker access tokens."""

    @staticmethod
    def parse_expiry_epoch_ms(jwt: str | None) -> int:
        if not jwt:
            return -1
        parts = jwt.split(".")
        if len(parts) < 2:
            return -1
        try:
            payload_bytes = base64.urlsafe_b64decode(_pad(parts[1]))
            payload = json.loads(payload_bytes.decode("utf-8"))
            exp = payload.get("exp")
            if exp is None:
                return -1
            return int(exp) * 1000
        except Exception:
            return -1

    @staticmethod
    def parse_expiry_datetime(jwt: str | None) -> datetime | None:
        """Return naive UTC datetime for the JWT ``exp`` claim, or None."""
        exp_ms = JwtExpiry.parse_expiry_epoch_ms(jwt)
        if exp_ms <= 0:
            return None
        return datetime.fromtimestamp(exp_ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _pad(value: str) -> str:
    remainder = len(value) % 4
    if remainder == 0:
        return value
    return value + "=" * (4 - remainder)
