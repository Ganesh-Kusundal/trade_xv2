"""Dhan integration test fixtures and live mutation guard."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from brokers.dhan import DhanBroker

INTEGRATION_ENV_VAR = "DHAN_INTEGRATION"


MUTATING_METHODS: tuple[tuple[str, ...], ...] = (
    ("place_order",),
    ("place_order_rest",),
    ("modify_order_rest",),
    ("cancel_order_rest",),
    ("subscribe_order_stream",),
    ("unsubscribe_order_stream",),
    ("place_slice_order_rest",),
    ("place_super_order_rest",),
    ("cancel_super_order_rest",),
    ("place_forever_order_rest",),
    ("cancel_forever_order_rest",),
    ("enable_pnl_exit_rest",),
    ("place_alert_rest",),
    ("delete_alert_rest",),
    ("order_command", "place_order"),
    ("order_command", "modify_order"),
    ("order_command", "cancel_order"),
    ("order_client", "place_order"),
    ("order_client", "modify_order"),
    ("order_client", "cancel_order"),
    ("order_client", "cancel_all_open_orders"),
    ("order_client", "place_slice_order"),
    ("order_client", "place_super_order"),
    ("order_client", "modify_super_order"),
    ("order_client", "cancel_super_order"),
    ("order_client", "place_forever_order"),
    ("order_client", "modify_forever_order"),
    ("order_client", "cancel_forever_order"),
    ("order_client", "set_kill_switch"),
    ("bracket_order", "place_super_order"),
    ("bracket_order", "modify_super_order"),
    ("bracket_order", "cancel_super_order"),
    ("cover_order", "place_cover_order"),
    ("cover_order", "exit_cover_order"),
    ("gtt_order", "place_forever_order"),
    ("gtt_order", "modify_forever_order"),
    ("gtt_order", "cancel_forever_order"),
    ("slice_order", "place_slice_order"),
    ("session_risk", "enable_pnl_exit"),
    ("conditional_alert", "place_alert"),
    ("conditional_alert", "delete_alert"),
)


def require_integration_enabled() -> None:
    if os.getenv(INTEGRATION_ENV_VAR) != "1":
        pytest.skip(f"set {INTEGRATION_ENV_VAR}=1 to run Dhan integration tests")


def clear_dhan_env() -> None:
    integration_enabled = os.getenv(INTEGRATION_ENV_VAR)
    for key in list(os.environ):
        if key.startswith("DHAN_"):
            os.environ.pop(key, None)
    if integration_enabled is not None:
        os.environ[INTEGRATION_ENV_VAR] = integration_enabled


def resolve_env_path(kind: str) -> Path:
    if kind == "sandbox":
        candidates = (Path(".env.local.sandbox"), Path(".env.local"))
    else:
        candidates = (Path(".env.local.live_readonly"), Path(".env.local"))

    for candidate in candidates:
        if candidate.exists():
            return candidate

    pytest.skip(f"missing Dhan env file: {' or '.join(str(c) for c in candidates)}")


def make_broker(env_path: Path) -> DhanBroker:
    clear_dhan_env()
    return DhanBroker.from_env(env_path=env_path)


def install_live_mutation_guard(monkeypatch: pytest.MonkeyPatch, broker: DhanBroker) -> None:
    for path in MUTATING_METHODS:
        target = _resolve_target(broker, path[:-1])
        method_name = path[-1]
        if target is None or not hasattr(target, method_name):
            continue
        monkeypatch.setattr(
            target,
            method_name,
            _blocked_method(".".join(path)),
            raising=False,
        )


def _blocked_method(method_name: str) -> Callable[..., Any]:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"Live mutation blocked: {method_name}")

    return blocked


def _resolve_target(root: Any, path: tuple[str, ...]) -> Any | None:
    target = root
    for part in path:
        if not hasattr(target, part):
            return None
        target = getattr(target, part)
    return target
