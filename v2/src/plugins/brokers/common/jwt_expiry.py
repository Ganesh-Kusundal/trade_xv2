"""Parse JWT ``exp`` without signature verification — mirror src JwtExpiry."""

from __future__ import annotations

import base64
import json
import time


class JwtExpiry:
    @staticmethod
    def parse_expiry_epoch(jwt: str | None) -> float:
        """Return JWT exp as unix seconds, or -1 if unparseable."""
        if not jwt:
            return -1.0
        parts = jwt.split(".")
        if len(parts) < 2:
            return -1.0
        try:
            payload = json.loads(base64.urlsafe_b64decode(_pad(parts[1])).decode())
            exp = payload.get("exp")
            if exp is None:
                return -1.0
            return float(exp)
        except Exception:
            return -1.0

    @staticmethod
    def is_valid(jwt: str | None, *, buffer_seconds: float = 0.0) -> bool:
        exp = JwtExpiry.parse_expiry_epoch(jwt)
        if exp < 0:
            return False
        return exp > (time.time() + buffer_seconds)


def _pad(value: str) -> str:
    rem = len(value) % 4
    return value if rem == 0 else value + ("=" * (4 - rem))
