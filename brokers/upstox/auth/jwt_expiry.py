"""Parses JWT ``exp`` claim from Upstox tokens without signature verification.

Delegates to shared :mod:`brokers.common.auth.jwt_expiry`.
"""

from __future__ import annotations

from brokers.common.auth.jwt_expiry import JwtExpiry


class UpstoxJwtExpiry:
    @staticmethod
    def parse_expiry_epoch_ms(jwt: str | None) -> int:
        return JwtExpiry.parse_expiry_epoch_ms(jwt)
