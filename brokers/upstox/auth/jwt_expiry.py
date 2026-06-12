"""Parses JWT ``exp`` claim from Upstox tokens without signature verification.

Mirrors Trade_J ``UpstoxJwtExpiry``.
"""

from __future__ import annotations

import base64
import json


class UpstoxJwtExpiry:
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


def _pad(value: str) -> str:
    remainder = len(value) % 4
    if remainder == 0:
        return value
    return value + "=" * (4 - remainder)
