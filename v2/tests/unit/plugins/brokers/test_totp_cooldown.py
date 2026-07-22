"""TOTP cooldown guard — blocks hammering broker login APIs."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.brokers.common.totp_cooldown import TotpCooldownGuard, TotpRateLimitError


def test_first_attempt_allowed(tmp_path: Path) -> None:
    guard = TotpCooldownGuard("dhan", cooldown_seconds=120.0, state_path=tmp_path / "cd.json")
    guard.check_allowed()
    guard.record_attempt()
    guard.record_success()


def test_rate_limited_blocks_until_cooldown(tmp_path: Path) -> None:
    path = tmp_path / "cd.json"
    guard = TotpCooldownGuard("dhan", cooldown_seconds=60.0, state_path=path)
    guard.record_rate_limited()
    with pytest.raises(TotpRateLimitError):
        guard.check_allowed()


def test_cooldown_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "cd.json"
    a = TotpCooldownGuard("upstox", cooldown_seconds=600.0, state_path=path)
    a.record_rate_limited()
    b = TotpCooldownGuard("upstox", cooldown_seconds=600.0, state_path=path)
    with pytest.raises(TotpRateLimitError):
        b.check_allowed()


def test_for_broker_returns_singleton() -> None:
    # ponytail: clear class cache between tests via private map
    TotpCooldownGuard._instances.clear()
    a = TotpCooldownGuard.for_broker("dhan", cooldown_seconds=1.0)
    b = TotpCooldownGuard.for_broker("dhan")
    assert a is b
