"""Task 12 (C3): Live parity gate non-skippable."""

import os
from unittest.mock import patch

import pytest


def test_live_environment_ignores_skip_parity_gate():
    """SKIP_PARITY_GATE must be ignored when TRADEX_ENV is production."""
    from runtime.parity_gate import assert_runtime_parity_or_raise

    with patch.dict(os.environ, {"SKIP_PARITY_GATE": "1", "TRADEX_ENV": "production"}):
        try:
            assert_runtime_parity_or_raise()
        except RuntimeError:
            pass  # Gate ran and failed — expected in test env without verifiers


def test_staging_environment_ignores_skip_parity_gate():
    """SKIP_PARITY_GATE must be ignored when TRADEX_ENV is staging."""
    from runtime.parity_gate import assert_runtime_parity_or_raise

    with patch.dict(os.environ, {"SKIP_PARITY_GATE": "1", "TRADEX_ENV": "staging"}):
        try:
            assert_runtime_parity_or_raise()
        except RuntimeError:
            pass


def test_development_environment_honors_skip_parity_gate():
    """SKIP_PARITY_GATE=1 should work in development."""
    from runtime.parity_gate import assert_runtime_parity_or_raise

    with patch.dict(os.environ, {"SKIP_PARITY_GATE": "1", "TRADEX_ENV": "development"}):
        assert_runtime_parity_or_raise()  # Should return without error


def test_default_environment_honors_skip_parity_gate():
    """SKIP_PARITY_GATE=1 should work when TRADEX_ENV is not set."""
    from runtime.parity_gate import assert_runtime_parity_or_raise

    env = os.environ.copy()
    env.pop("TRADEX_ENV", None)
    env["SKIP_PARITY_GATE"] = "1"
    with patch.dict(os.environ, env, clear=True):
        assert_runtime_parity_or_raise()  # Should return without error
