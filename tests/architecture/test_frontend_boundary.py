"""ADR-0022 — Frontend boundary architecture ratchet."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADR_0022 = _REPO_ROOT / "docs/architecture/adr/0022-frontend-boundary.md"


@pytest.mark.architecture
def test_adr_0022_frontend_boundary_exists_and_accepted():
    assert _ADR_0022.is_file(), "ADR-0022 frontend boundary document must exist"
    text = _ADR_0022.read_text(encoding="utf-8")
    assert "Accepted" in text
    assert "0020-operator-api-hardening.md" in text


@pytest.mark.architecture
@pytest.mark.parametrize(
    "module_name",
    ["interface.api.ws.market", "interface.api.ws.replay"],
)
def test_ws_module_endpoints_call_reject_ws_if_unauthorized(module_name: str):
    import importlib

    module = importlib.import_module(module_name)
    src = inspect.getsource(module)
    ws_count = src.count("@router.websocket")
    auth_count = src.count("reject_ws_if_unauthorized")
    assert ws_count > 0, f"{module_name} must define WebSocket routes"
    assert auth_count >= ws_count, (
        f"{module_name}: each @router.websocket handler must call "
        "reject_ws_if_unauthorized before accept"
    )
