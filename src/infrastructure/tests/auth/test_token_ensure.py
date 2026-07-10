"""Tests for ensure_access_token — probe-before-mint policy."""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from infrastructure.auth.token import JsonTokenStateStore, TokenSource, TokenState
from infrastructure.auth.token_ensure import ensure_access_token
from infrastructure.auth.totp_cooldown import TotpRateLimitError


def _jwt(exp_offset_s: int) -> str:
    header = base64.b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = (
        base64.b64encode(json.dumps({"exp": int(time.time()) + exp_offset_s}).encode())
        .decode()
        .rstrip("=")
    )
    return f"{header}.{body}.sig"


def test_reuses_valid_store_token_without_mint(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    valid = _jwt(7200)
    store.save(
        TokenState(
            access_token=valid,
            source=TokenSource.TOTP,
            expires_at=datetime.now() + timedelta(hours=2),
        )
    )
    calls = {"n": 0}

    def mint() -> str | None:
        calls["n"] += 1
        return "minted"

    state = ensure_access_token(store=store, env_token=None, mint=mint)
    assert calls["n"] == 0
    assert state is not None
    assert state.access_token == valid


def test_reuses_valid_env_token_without_mint(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    valid = _jwt(3600)
    calls = {"n": 0}

    def mint() -> str | None:
        calls["n"] += 1
        return "minted"

    state = ensure_access_token(store=store, env_token=valid, mint=mint)
    assert calls["n"] == 0
    assert state is not None
    assert state.access_token == valid


def test_mints_once_when_missing(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    fresh = _jwt(7200)
    calls = {"n": 0}

    def mint() -> str | None:
        calls["n"] += 1
        return fresh

    state = ensure_access_token(store=store, env_token=None, mint=mint)
    assert calls["n"] == 1
    assert state is not None
    assert state.access_token == fresh
    # persisted
    loaded = store.load()
    assert loaded is not None
    assert loaded.access_token == fresh


def test_mints_once_when_expired(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    store.save(
        TokenState(
            access_token=_jwt(-60),
            source=TokenSource.TOTP,
            expires_at=datetime.now() - timedelta(minutes=1),
        )
    )
    fresh = _jwt(7200)
    calls = {"n": 0}

    def mint() -> str | None:
        calls["n"] += 1
        return fresh

    state = ensure_access_token(store=store, env_token=None, mint=mint)
    assert calls["n"] == 1
    assert state is not None
    assert state.access_token == fresh


def test_broker_rejected_clears_store_and_mints(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    rejected = _jwt(7200)  # still looks valid locally
    store.save(
        TokenState(
            access_token=rejected,
            source=TokenSource.TOTP,
            expires_at=datetime.now() + timedelta(hours=2),
        )
    )
    fresh = _jwt(8000)  # different exp → different JWT payload
    calls = {"n": 0}

    def mint() -> str | None:
        calls["n"] += 1
        return fresh

    state = ensure_access_token(
        store=store,
        env_token=rejected,
        mint=mint,
        broker_rejected=True,
    )
    assert calls["n"] == 1
    assert state is not None
    assert state.access_token == fresh
    assert state.access_token != rejected


def test_mint_failure_returns_none(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")

    def mint() -> str | None:
        return None

    assert ensure_access_token(store=store, mint=mint) is None


def test_mint_raises_propagates(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")

    def mint() -> str | None:
        raise TotpRateLimitError("cooldown")

    with pytest.raises(TotpRateLimitError):
        ensure_access_token(store=store, mint=mint)


def test_persists_to_env_file(tmp_path: Path):
    store = JsonTokenStateStore(tmp_path / "tok.json")
    env = tmp_path / ".env.local"
    env.write_text("DHAN_CLIENT_ID=x\nDHAN_ACCESS_TOKEN=old\n")
    fresh = _jwt(7200)

    def mint() -> str | None:
        return fresh

    ensure_access_token(
        store=store,
        env_token="old",
        mint=mint,
        env_path=env,
        env_key="DHAN_ACCESS_TOKEN",
        broker_rejected=True,  # force mint despite env present
    )
    text = env.read_text()
    assert f"DHAN_ACCESS_TOKEN={fresh}" in text
