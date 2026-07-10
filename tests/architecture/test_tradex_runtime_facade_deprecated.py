"""Facade modules under tradex.runtime must warn on import."""

from __future__ import annotations

import importlib
import sys
import warnings

import pytest


def _clear_runtime_modules() -> None:
    """Drop facade modules and reset once-only warning state."""
    for name in list(sys.modules):
        if name == "tradex.runtime" or name.startswith("tradex.runtime."):
            del sys.modules[name]
    # Load deprecation helper without executing package ``__init__`` (which would
    # re-import facades and re-arm ``_SEEN``).
    import tradex.runtime._deprecation as dep

    dep._SEEN.clear()
    # Drop anything the helper import pulled in under tradex.runtime again.
    for name in list(sys.modules):
        if name == "tradex.runtime" or name.startswith("tradex.runtime."):
            if name == "tradex.runtime._deprecation":
                continue
            del sys.modules[name]


@pytest.mark.parametrize(
    ("module", "canonical_substr"),
    [
        ("tradex.runtime.router", "application.composer.router"),
        ("tradex.runtime.broker_port", "domain.ports.broker_gateway"),
        ("tradex.runtime.resilience.circuit_breaker", "infrastructure.resilience"),
    ],
)
def test_facade_import_emits_deprecation(module: str, canonical_substr: str) -> None:
    _clear_runtime_modules()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module(module)

    messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any(
        "deprecated compatibility facade" in m and canonical_substr in m for m in messages
    ), f"expected facade DeprecationWarning for {module}, got: {messages}"
