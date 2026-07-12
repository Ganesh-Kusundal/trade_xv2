"""Tests for parity gate LIVE-environment non-skippable behaviour (Task 12).

The parity gate must NOT honour ``SKIP_PARITY_GATE=1`` when ``TRADEX_ENV``
is ``production`` or ``staging``.  In non-live environments the skip flag
continues to work as before.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# LIVE environment: SKIP_PARITY_GATE must be ignored
# ---------------------------------------------------------------------------

class TestLiveParityGateNotSkippable:
    """In production/staging the gate always runs regardless of SKIP_PARITY_GATE."""

    def test_production_ignores_skip_parity_gate_and_raises_on_failure(
        self, monkeypatch
    ):
        monkeypatch.setenv("TRADEX_ENV", "production")
        monkeypatch.setenv("SKIP_PARITY_GATE", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from runtime.parity_gate import assert_runtime_parity_or_raise

        # Mock subprocess so the gate actually runs but fails deterministically
        import subprocess

        fake_result = type("R", (), {"returncode": 1, "stderr": "parity fail", "stdout": ""})()
        with patch.object(subprocess, "run", return_value=fake_result):
            with pytest.raises(RuntimeError, match="Runtime parity gate failed"):
                assert_runtime_parity_or_raise()

    def test_staging_ignores_skip_parity_gate_and_raises_on_failure(
        self, monkeypatch
    ):
        monkeypatch.setenv("TRADEX_ENV", "staging")
        monkeypatch.setenv("SKIP_PARITY_GATE", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from runtime.parity_gate import assert_runtime_parity_or_raise

        import subprocess

        fake_result = type("R", (), {"returncode": 1, "stderr": "parity fail", "stdout": ""})()
        with patch.object(subprocess, "run", return_value=fake_result):
            with pytest.raises(RuntimeError, match="Runtime parity gate failed"):
                assert_runtime_parity_or_raise()

    def test_production_runs_gate_without_skip_flag(self, monkeypatch):
        """Even without SKIP_PARITY_GATE the gate runs in production (sanity)."""
        monkeypatch.setenv("TRADEX_ENV", "production")
        monkeypatch.delenv("SKIP_PARITY_GATE", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from runtime.parity_gate import assert_runtime_parity_or_raise

        import subprocess

        fake_result = type("R", (), {"returncode": 1, "stderr": "fail", "stdout": ""})()
        with patch.object(subprocess, "run", return_value=fake_result):
            with pytest.raises(RuntimeError, match="Runtime parity gate failed"):
                assert_runtime_parity_or_raise()


# ---------------------------------------------------------------------------
# Non-LIVE environment: SKIP_PARITY_GATE still honoured
# ---------------------------------------------------------------------------

class TestNonLiveParityGateSkippable:
    """In development / unset environments the skip flag works as before."""

    def test_development_honours_skip_parity_gate(self, monkeypatch):
        monkeypatch.setenv("TRADEX_ENV", "development")
        monkeypatch.setenv("SKIP_PARITY_GATE", "1")

        from runtime.parity_gate import assert_runtime_parity_or_raise

        # Should return silently — gate is skipped
        assert_runtime_parity_or_raise()

    def test_unset_env_honours_skip_parity_gate(self, monkeypatch):
        monkeypatch.delenv("TRADEX_ENV", raising=False)
        monkeypatch.setenv("SKIP_PARITY_GATE", "1")

        from runtime.parity_gate import assert_runtime_parity_or_raise

        # Should return silently — gate is skipped
        assert_runtime_parity_or_raise()

    def test_development_without_skip_runs_gate(self, monkeypatch):
        """Without SKIP_PARITY_GATE, the gate runs in development too."""
        monkeypatch.setenv("TRADEX_ENV", "development")
        monkeypatch.delenv("SKIP_PARITY_GATE", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        from runtime.parity_gate import assert_runtime_parity_or_raise

        import subprocess

        fake_result = type("R", (), {"returncode": 1, "stderr": "fail", "stdout": ""})()
        with patch.object(subprocess, "run", return_value=fake_result):
            with pytest.raises(RuntimeError, match="Runtime parity gate failed"):
                assert_runtime_parity_or_raise()
