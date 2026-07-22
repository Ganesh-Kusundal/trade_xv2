"""ADR-0013 R15 — live execution lift prep ratchets (flags off by default)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.ports.execution_target import ExecutionTargetKind
from runtime.execution_config import (
    assert_live_lift_preconditions,
    requested_live_execution_target,
    resolve_execution_target_kind,
)
from runtime.execution_target import resolve_execution_target


@pytest.fixture(autouse=True)
def _clear_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "TRADEX_EXECUTION_TARGET",
        "TRADEX_ENABLE_LIVE_EXECUTION",
        "TRADEX_ADR_0013_LIFT",
        "TRADEX_LIVE_PREDEPLOY_SCORE",
        "TRADEX_CHAOS_GREEN_STREAK",
    ):
        monkeypatch.delenv(key, raising=False)


def test_paper_default_unchanged() -> None:
    assert resolve_execution_target_kind() is ExecutionTargetKind.PAPER
    assert not requested_live_execution_target()


def test_live_blocked_without_flags() -> None:
    with pytest.raises(RuntimeError, match="ADR-0013"):
        resolve_execution_target_kind(ExecutionTargetKind.LIVE)


def test_enable_live_flag_alone_insufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_ENABLE_LIVE_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="TRADEX_ADR_0013_LIFT"):
        assert_live_lift_preconditions()


def test_double_opt_in_still_blocked_by_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_ENABLE_LIVE_EXECUTION", "1")
    monkeypatch.setenv("TRADEX_ADR_0013_LIFT", "1")
    with pytest.raises(RuntimeError, match="PRE-DEPLOY"):
        assert_live_lift_preconditions()


def test_gates_met_allows_assert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_ENABLE_LIVE_EXECUTION", "1")
    monkeypatch.setenv("TRADEX_ADR_0013_LIFT", "1")
    monkeypatch.setenv("TRADEX_LIVE_PREDEPLOY_SCORE", "8.5")
    monkeypatch.setenv("TRADEX_CHAOS_GREEN_STREAK", "4")
    assert_live_lift_preconditions()


def test_resolve_live_kind_requires_preconditions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_ENABLE_LIVE_EXECUTION", "1")
    monkeypatch.setenv("TRADEX_ADR_0013_LIFT", "1")
    monkeypatch.setenv("TRADEX_LIVE_PREDEPLOY_SCORE", "8.5")
    monkeypatch.setenv("TRADEX_CHAOS_GREEN_STREAK", "4")
    assert resolve_execution_target_kind(ExecutionTargetKind.LIVE) is ExecutionTargetKind.LIVE


def test_execution_target_resolver_live_fail_closed() -> None:
    gateway = MagicMock()
    with pytest.raises(RuntimeError, match="ADR-0013"):
        resolve_execution_target(ExecutionTargetKind.LIVE, gateway=gateway)


def test_requested_live_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEX_EXECUTION_TARGET", "live")
    assert requested_live_execution_target() is True


@pytest.mark.architecture
def test_execution_config_exports_lift_preconditions() -> None:
    from runtime import execution_config

    assert hasattr(execution_config, "assert_live_lift_preconditions")
    assert hasattr(execution_config, "requested_live_execution_target")
