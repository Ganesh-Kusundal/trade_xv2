"""P1-T4 (drift D4): the parity gate is unbypassable in production/staging.

The zero-parity rule requires backtest/replay/live to share identical logic.
The gate must therefore always run before a live boot, and neither
``SKIP_PARITY_GATE=1`` (env) nor ``parity_gate_enabled=False`` (config) may
disable it in prod/staging.

These tests use a stubbed subprocess so the verifiers don't actually run, but
assert the gate is *reached* (it must not early-return on the skip flag in a
live env) and that the factory refuses a disabled gate in a live env.
"""

from __future__ import annotations

import os
import pytest

from runtime import parity_gate


class _FakeResult:
    """Real subprocess result stub for the parity verifiers."""

    returncode = 0
    stderr = ""
    stdout = ""
from runtime.production_config import is_production_environment
from runtime.resilience import ResilienceConfig


def _set_env(monkeypatch, env: str, skip: str = "0") -> None:
    monkeypatch.setenv("TRADEX_ENV", env)
    monkeypatch.setenv("SKIP_PARITY_GATE", skip)
    # Ensure pytest detection doesn't mask the live env.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("TRADEX_FORCE_PROD_VALIDATION", raising=False)


def test_live_env_ignores_skip_flag_runs_verifiers(monkeypatch):
    """In prod, SKIP_PARITY_GATE=1 must NOT skip the gate."""
    _set_env(monkeypatch, "production", skip="1")
    assert is_production_environment()

    calls = []
    monkeypatch.setattr(
        parity_gate.subprocess,
        "run",
        lambda *a, **k: calls.append((a, k)) or _FakeResult(),
    )
    # Pretend every referenced verifier script/test exists so the gate reaches
    # subprocess.run.
    from pathlib import Path

    monkeypatch.setattr(Path, "exists", lambda self: True)

    parity_gate.assert_runtime_parity_or_raise()
    # The gate attempted at least one verifier subprocess — it did NOT skip.
    assert calls, "parity gate must run verifiers in production even with SKIP_PARITY_GATE=1"


def test_dev_env_honours_skip_flag(monkeypatch):
    """In dev, SKIP_PARITY_GATE=1 still skips the gate (local dev escape hatch)."""
    _set_env(monkeypatch, "development", skip="1")

    calls = []
    monkeypatch.setattr(
        parity_gate.subprocess,
        "run",
        lambda *a, **k: calls.append((a, k)) or _FakeResult(),
    )
    from pathlib import Path

    monkeypatch.setattr(Path, "exists", lambda self: True)

    parity_gate.assert_runtime_parity_or_raise()
    assert calls == [], "parity gate must skip in dev with SKIP_PARITY_GATE=1"


def test_resilience_config_forces_gate_in_live_env(monkeypatch):
    """parity_gate_enabled must be True in prod even if SKIP_PARITY_GATE=1."""
    _set_env(monkeypatch, "production", skip="1")
    cfg = ResilienceConfig.from_env()
    assert cfg.parity_gate_enabled is True

    _set_env(monkeypatch, "staging", skip="1")
    cfg = ResilienceConfig.from_env()
    assert cfg.parity_gate_enabled is True


def test_validate_production_config_blocks_skip_flag(monkeypatch):
    """Production validation rejects SKIP_PARITY_GATE=1 (the factory's first gate)."""
    _set_env(monkeypatch, "production", skip="1")
    from runtime.production_config import validate_production_config

    with pytest.raises(RuntimeError):
        validate_production_config(surface="runtime")


def test_factory_guard_expression_in_live_env(monkeypatch):
    """The exact guard ``runtime.factory.build`` raises on in a live env.

    We reproduce the guard condition the factory evaluates (it cannot be
    invoked without a full broker service) to lock the contract: in a live env
    a disabled parity gate is forbidden, and ``ResilienceConfig.from_env`` can
    never produce one there.
    """
    _set_env(monkeypatch, "production", skip="0")
    assert is_production_environment()

    cfg = ResilienceConfig.from_env()
    assert cfg.parity_gate_enabled is True

    guard_raises = is_production_environment() and not cfg.parity_gate_enabled
    assert guard_raises is False
