"""ADR-001 — guard against orphaned root-level broker shadow modules.

The repo previously carried divergent duplicates of ``src/brokers/providers/dhan/*`` at the
repo root (``brokers/providers/dhan/gateway.py``, ``brokers/providers/dhan/orders.py``). They were kept
from shadowing ``src/`` only by ``src/brokers/_bootstrap.py`` force-inserting ``src/``
first on ``sys.path``. A path-order regression would silently import the stale copy.

This test makes that impossible to miss:
- an actual ``src/`` module (``brokers.providers.dhan.wire``) must resolve under ``src/``;
- the formerly-shadowed names (``gateway``, ``orders``) must not exist under
  ``brokers.providers.dhan`` at all;
- no ``*.py`` may exist under a repo-root ``brokers/providers/dhan/`` directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import brokers.providers.dhan.wire as wire_module

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.architecture
def test_dhan_wire_resolves_to_src() -> None:
    """Importing a real src/ module must resolve to the src/ implementation."""
    resolved = Path(wire_module.__file__).resolve()
    assert "src/brokers/providers/dhan/wire.py" in str(resolved), resolved


@pytest.mark.architecture
def test_no_shadow_dhan_module_names() -> None:
    """The orphaned shadow module names must not exist under brokers.providers.dhan."""
    import brokers.providers.dhan as dhan_pkg

    offenders = [
        name
        for name in ("gateway", "orders")
        if hasattr(dhan_pkg, name) or (Path(dhan_pkg.__file__).parent / f"{name}.py").exists()
    ]
    assert not offenders, f"shadow dhan module names present: {offenders}"


@pytest.mark.architecture
def test_no_root_shadow_broker_modules() -> None:
    """No *.py shadow modules may exist under a repo-root brokers/providers/dhan/ directory."""
    shadow = _REPO_ROOT / "brokers" / "dhan"
    if not shadow.exists():
        return
    offenders = sorted(p.name for p in shadow.glob("*.py"))
    assert not offenders, f"shadow broker modules found: {offenders}"
