"""R12 — deployment artifact architecture ratchets."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.architecture
def test_dockerfile_exists_and_is_multi_stage():
    dockerfile = ROOT / "Dockerfile"
    assert dockerfile.is_file()
    src = dockerfile.read_text(encoding="utf-8")
    assert "AS builder" in src
    assert "AS runtime" in src
    assert "USER tradex" in src


@pytest.mark.architecture
def test_dockerfile_declares_state_volume():
    src = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "TRADEX_STATE_ROOT" in src
    assert "/var/lib/tradex/state" in src


@pytest.mark.architecture
def test_session_recorder_uses_state_root_env():
    from infrastructure.observability.session_recorder import resolve_session_recording_dir

    import os

    prev = os.environ.get("TRADEX_STATE_ROOT")
    try:
        os.environ["TRADEX_STATE_ROOT"] = "/tmp/tradex-state-test"
        assert resolve_session_recording_dir() == Path("/tmp/tradex-state-test/session-recordings")
    finally:
        if prev is None:
            os.environ.pop("TRADEX_STATE_ROOT", None)
        else:
            os.environ["TRADEX_STATE_ROOT"] = prev


@pytest.mark.architecture
def test_observability_bind_reads_env():
    from interface.ui.services import oms_bootstrap

    src = oms_bootstrap.__file__
    assert src
    text = Path(src).read_text(encoding="utf-8")
    assert "TRADEX_OBSERVABILITY_HOST" in text
    assert "TRADEX_OBSERVABILITY_PORT" in text


@pytest.mark.architecture
def test_docker_smoke_workflow_exists():
    workflow = ROOT / ".github" / "workflows" / "docker-smoke.yml"
    assert workflow.is_file()
    src = workflow.read_text(encoding="utf-8")
    assert "docker build" in src
    assert "health" in src.lower()
