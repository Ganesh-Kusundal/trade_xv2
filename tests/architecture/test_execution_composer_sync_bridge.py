"""P0-2 — ExecutionComposer sync/async bridge and fail-closed cancel default."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXECUTION_COMPOSER = ROOT / "src" / "application" / "composer" / "execution.py"


def test_execution_composer_does_not_use_asyncio_run() -> None:
    source = EXECUTION_COMPOSER.read_text(encoding="utf-8")
    assert "asyncio.run" not in source, (
        "ExecutionComposer must bridge async gateways via run_coro_sync, not asyncio.run"
    )
    assert "run_coro_sync" in source


def test_cancel_fn_fail_closed_when_success_missing() -> None:
    source = EXECUTION_COMPOSER.read_text(encoding="utf-8")
    assert 'getattr(resp, "success", False)' in source, (
        "cancel_fn must default success to False (fail-closed)"
    )
    assert 'getattr(resp, "success", True)' not in source


def test_place_via_oms_uses_injected_execution_target_kind() -> None:
    source = EXECUTION_COMPOSER.read_text(encoding="utf-8")
    assert "ExecutionTargetKind.LIVE" not in source, (
        "_place_via_oms must not hardcode LIVE; use injected execution_target_kind"
    )
    assert "self._execution_target_kind" in source
    assert "execution_target_kind" in source
