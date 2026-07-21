"""Tests for domain.constants facade purity (REF-13)."""

import ast

from domain.constants import __all__


def test_constants_init_is_pure_facade():
    """__init__.py should contain only imports — no class or function definitions."""
    with open("src/domain/constants/__init__.py") as f:
        tree = ast.parse(f.read())
    # Should only have imports, no class/function definitions
    for node in ast.iter_child_nodes(tree):
        assert isinstance(node, (ast.Import, ast.ImportFrom)), (
            f"Non-import node found: {type(node).__name__}"
        )


def test_all_exports_are_imports():
    """Every name in __all__ should be importable from the package."""
    import domain.constants as const_mod

    for name in __all__:
        assert hasattr(const_mod, name), f"{name} in __all__ but not importable"


def test_oms_submodule_exists():
    """oms.py submodule should exist and export expected names."""
    from domain.constants.oms import BATCH_MAX_WORKERS, SECONDS_PER_HOUR

    assert SECONDS_PER_HOUR == 3600
    assert BATCH_MAX_WORKERS == 5


def test_reconciliation_submodule_exists():
    """reconciliation.py submodule should exist and export expected names."""
    from domain.constants.reconciliation import (
        DAILY_PNL_POLL_INTERVAL_SECONDS,
        RECONCILIATION_INTERVAL_SECONDS,
    )

    assert RECONCILIATION_INTERVAL_SECONDS == 300.0
    assert DAILY_PNL_POLL_INTERVAL_SECONDS == 60.0


def test_instrumentation_submodule_exists():
    """instrumentation.py submodule should exist and export expected names."""
    from domain.constants.instrumentation import DEFAULT_LOG_LEVEL

    assert DEFAULT_LOG_LEVEL == "INFO"


def test_history_submodule_exists():
    """history.py submodule should exist and export expected names."""
    from domain.constants.history import DEFAULT_HISTORY_PAGE_DAYS

    assert DEFAULT_HISTORY_PAGE_DAYS == 365


def test_no_analytics_shared_trade_types():
    """analytics.shared.trade_types should no longer exist."""
    import importlib

    try:
        importlib.import_module("analytics.shared.trade_types")
        # If we get here, the module exists — which is wrong
        assert False, "analytics.shared.trade_types should have been removed"
    except (ImportError, ModuleNotFoundError):
        pass  # Expected
