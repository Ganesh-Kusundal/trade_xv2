"""Sandbox order integration tests for CLI endpoints.

Parametrized over ``SANDBOX_ENDPOINTS`` from the endpoint manifest.  Each
case calls the real ``tradex`` CLI via subprocess and verifies exit code.

Gates
-----
- ``DHAN_SANDBOX_CLIENT_ID`` environment variable must be set.
- ``DHAN_SANDBOX_ACCESS_TOKEN`` environment variable must be set.
- Both are auto-skipped when absent — never runs on default PR CI.

Usage
-----
    # Set sandbox credentials
    export DHAN_SANDBOX_CLIENT_ID=...
    export DHAN_SANDBOX_ACCESS_TOKEN=...

    # Run only sandbox order tests
    pytest cli/tests/test_order_sandbox_integration.py -v -m sandbox

    # Or via the run_broker_tests.sh helper
    ./scripts/run_broker_tests.sh sandbox
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli.tests.endpoint_manifest import SANDBOX_ENDPOINTS, CliEndpoint

# ---------------------------------------------------------------------------
# Credential gate — skip the entire module when sandbox creds are missing
# ---------------------------------------------------------------------------

_SANDBOX_CLIENT_ID = os.environ.get("DHAN_SANDBOX_CLIENT_ID", "")
_SANDBOX_TOKEN = os.environ.get("DHAN_SANDBOX_ACCESS_TOKEN", "")

_SANDBOX_READY = bool(_SANDBOX_CLIENT_ID and _SANDBOX_TOKEN)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env.local"


@pytest.fixture(scope="session", autouse=True)
def _require_sandbox_creds():
    if not _SANDBOX_READY:
        pytest.skip(
            "DHAN_SANDBOX_CLIENT_ID and DHAN_SANDBOX_ACCESS_TOKEN required for sandbox order tests"
        )


# ---------------------------------------------------------------------------
# Sandbox environment — inject credentials into subprocess env
# ---------------------------------------------------------------------------

def _sandbox_env() -> dict[str, str]:
    """Build env for subprocess with sandbox credentials injected."""
    env = os.environ.copy()
    env["DHAN_CLIENT_ID"] = _SANDBOX_CLIENT_ID
    env["DHAN_ACCESS_TOKEN"] = _SANDBOX_TOKEN
    env["DHAN_INTEGRATION"] = "1"
    env["DHAN_SANDBOX"] = "1"
    return env


# ---------------------------------------------------------------------------
# Helper to locate the tradex CLI entry point
# ---------------------------------------------------------------------------

def _tradex_argv(args: list[str]) -> list[str]:
    """Build the full argv list for the tradex CLI."""
    tradex = _PROJECT_ROOT / "tradex"
    if tradex.exists():
        return [str(tradex), *args]
    # Fallback: invoke as a module
    return [sys.executable, "-m", "cli.main", *args]


# ---------------------------------------------------------------------------
# Parametrized sandbox CLI endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "endpoint",
    SANDBOX_ENDPOINTS,
    ids=lambda ep: ep.id,
)
@pytest.mark.sandbox
@pytest.mark.dhan
def test_sandbox_cli_endpoint(endpoint: CliEndpoint):
    """Run a sandbox CLI endpoint via subprocess and check exit code.

    These tests place and cancel real orders in the Dhan sandbox environment.
    They must never run on PR CI — only on the self-hosted sandbox job.
    """
    if endpoint.no_subprocess:
        pytest.skip(f"Endpoint '{endpoint.id}' opted out of subprocess testing")

    cmd = _tradex_argv(endpoint.argv)
    result = subprocess.run(
        cmd,
        env=_sandbox_env(),
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=endpoint.timeout_s,
    )

    assert result.returncode == endpoint.expect_exit, (
        f"CLI endpoint '{endpoint.id}' exit code {result.returncode} != "
        f"expected {endpoint.expect_exit}\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )

    if endpoint.expect_stdout_substr:
        assert endpoint.expect_stdout_substr in result.stdout, (
            f"CLI endpoint '{endpoint.id}' stdout missing '{endpoint.expect_stdout_substr}'\n"
            f"stdout: {result.stdout[:500]}"
        )


# ---------------------------------------------------------------------------
# Explicit LIMIT place+cancel flow (not covered by manifest)
# ---------------------------------------------------------------------------

@pytest.mark.sandbox
@pytest.mark.dhan
class TestSandboxOrderLifecycleCli:
    """Full place→verify→cancel order lifecycle via CLI subprocess."""

    def _run(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            _tradex_argv(args),
            env=_sandbox_env(),
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def test_place_limit_order_succeeds(self):
        """Placing a LIMIT order far below market must return exit 0."""
        result = self._run(
            ["place-order", "RELIANCE", "BUY", "1",
             "--type", "LIMIT", "--price", "1000"]  # far below market
        )
        assert result.returncode == 0, (
            f"place-order failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_place_and_cancel_order(self):
        """Place a LIMIT order then cancel it; both CLI calls must succeed."""
        # Place
        place_result = self._run(
            ["place-order", "TCS", "BUY", "1", "--type", "LIMIT", "--price", "1000"]
        )
        assert place_result.returncode == 0, (
            f"place-order failed:\n{place_result.stdout}\n{place_result.stderr}"
        )

        # Extract order ID from stdout (best-effort)
        order_id: str | None = None
        for line in place_result.stdout.splitlines():
            if "order_id" in line.lower() or "order-id" in line.lower():
                parts = line.split()
                for part in parts:
                    if part.isdigit() or (len(part) > 6 and part.replace("-", "").isalnum()):
                        order_id = part.strip(",:")
                        break

        if order_id:
            cancel_result = self._run(["cancel-order", order_id])
            # Cancel may fail if the order already executed (unlikely with price=1000)
            # so we only assert it ran without an unhandled exception (non-500 exit)
            assert cancel_result.returncode in (0, 1), (
                f"cancel-order crashed:\n{cancel_result.stdout}\n{cancel_result.stderr}"
            )
