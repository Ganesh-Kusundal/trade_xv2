from __future__ import annotations

import time

import jwt as pyjwt

from brokers.upstox.auth.jwt_expiry import UpstoxJwtExpiry


def _make_jwt(exp_seconds: int) -> str:
    return pyjwt.encode({"sub": "x", "exp": exp_seconds}, "secret", algorithm="HS256")


def test_jwt_expiry_parses_exp_claim():
    exp = int(time.time()) + 3600
    token = _make_jwt(exp)
    ms = UpstoxJwtExpiry.parse_expiry_epoch_ms(token)
    assert abs(ms - exp * 1000) < 1000


def test_jwt_expiry_returns_minus_one_for_invalid_token():
    assert UpstoxJwtExpiry.parse_expiry_epoch_ms("not.a.jwt") == -1
    assert UpstoxJwtExpiry.parse_expiry_epoch_ms("") == -1
    assert UpstoxJwtExpiry.parse_expiry_epoch_ms(None) == -1


def test_jwt_expiry_without_exp_claim():
    token = pyjwt.encode({"sub": "x"}, "secret", algorithm="HS256")
    assert UpstoxJwtExpiry.parse_expiry_epoch_ms(token) == -1
