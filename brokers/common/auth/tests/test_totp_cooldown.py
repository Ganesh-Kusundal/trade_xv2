"""Tests for TOTP cooldown guard."""

from __future__ import annotations

import pytest

from brokers.common.auth.totp_cooldown import TotpCooldownGuard, TotpRateLimitError


def test_cooldown_blocks_second_attempt(tmp_path):
    guard = TotpCooldownGuard("test", cooldown_seconds=120.0, state_path=tmp_path / "cooldown.json")
    guard.record_attempt()
    with pytest.raises(TotpRateLimitError):
        guard.check_allowed()


def test_cooldown_allows_after_success_recorded(tmp_path):
    guard = TotpCooldownGuard(
        "test2", cooldown_seconds=120.0, state_path=tmp_path / "cooldown2.json"
    )
    guard.record_success()
    with pytest.raises(TotpRateLimitError):
        guard.check_allowed()


def test_for_broker_returns_singleton():
    a = TotpCooldownGuard.for_broker("dhan", cooldown_seconds=120.0)
    b = TotpCooldownGuard.for_broker("dhan", cooldown_seconds=120.0)
    assert a is b
