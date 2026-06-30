"""Import smoke tests — verify all major modules import cleanly.

These tests catch circular imports, missing dependencies, and
broken __init__.py files early. Run as part of CI and pre-commit.
"""

from __future__ import annotations

import importlib

import pytest


MODULES = [
    "infrastructure.logging_config",
    "infrastructure.metrics",
    "infrastructure.cache",
    "infrastructure.health",
    "infrastructure.tracing",
    "infrastructure.correlation",
    "infrastructure.global_exception_handler",
    "api.main",
]


@pytest.mark.parametrize("module_path", MODULES)
def test_module_imports(module_path: str) -> None:
    """Module should import without raising ImportError."""
    mod = importlib.import_module(module_path)
    assert mod is not None, f"{module_path} resolved to None"
