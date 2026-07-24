"""Regression: unparseable-but-JWT-shaped tokens must be rejected (Bug 2 fix).

A corrupt token that *looks* like a JWT (header.payload.signature) but
can't be base64-decoded must NOT be trusted forever. Genuine
non-JWT static tokens (no dots) stay usable until the broker rejects.
"""

from __future__ import annotations

import sys

if sys.path.insert(0, "src") or True:  # ensure src importable under uv
    pass

from plugins.brokers.common.jwt_expiry import JwtExpiry
from plugins.brokers.dhan.auth import _token_usable
from plugins.brokers.upstox.auth import _access_token_usable


# A valid JWT with exp in the past -> unusable
_PAST_JWT = (
    "eyJhbGciOiJIUzI1NiJ9."
    "eyJleHAiOjAsfX0sLCJzdWIiOiIxMjM0NTY2Nzg5In0."
    "SflKxwRJSMeKKF2QT4fWzdl1BfaSClZ2xL6mU"
)


def test_parse_expiry_rejects_unparseable() -> None:
    # Header/payload not valid base64 JSON -> -1 (no info)
    assert JwtExpiry.parse_expiry_epoch("not-a-jwt") == -1.0
    assert JwtExpiry.parse_expiry_epoch("a.b.c") == -1.0


def test_is_jwt_like() -> None:
    assert JwtExpiry.is_jwt_like("a.b.c") is True
    # Only 2 segments -> not JWT-shaped
    assert JwtExpiry.is_jwt_like("a.b") is False
    assert JwtExpiry.is_jwt_like("") is False
    assert JwtExpiry.is_jwt_like(None) is False
    # Garbage 3-segment string -> still JWT-LIKE (shape), just undecodeable
    assert JwtExpiry.is_jwt_like("@@@.###.$$$") is True


def test_corrupt_jwt_rejected_dhan() -> None:
    # Looks like a JWT (3 dots... 3 segments) but can't decode -> reject.
    assert _token_usable("@@@.###.$$$") is False


def test_corrupt_jwt_rejected_upstox() -> None:
    assert _access_token_usable("@@@.###.$$$") is False


def test_static_non_jwt_token_still_usable_dhan() -> None:
    # A plain static access token (no dots) is trusted until broker rejects.
    assert _token_usable("static-plain-token-value") is True


def test_static_non_jwt_token_still_usable_upstox() -> None:
    assert _access_token_usable("static-plain-token-value") is True


def test_valid_past_jwt_unusable() -> None:
    assert _token_usable(_PAST_JWT) is False
    assert _access_token_usable(_PAST_JWT) is False
