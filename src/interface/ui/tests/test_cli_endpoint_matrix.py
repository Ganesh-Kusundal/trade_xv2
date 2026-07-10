"""Subprocess endpoint matrix — T1.

Drives the offline endpoints declared in
:mod:`cli.tests.endpoint_manifest` through the real ``cli.main``
router using ``python -m interface.ui.main``.  Each endpoint must:

* exit with the declared code,
* not raise an unhandled exception (asserted by exit code 0/1),
* match its expected stdout/stderr substring when provided.

Why a subprocess and not an in-process call?
-------------------------------------------
* Exercises the full argv parsing, ``_NO_GATEWAY_CMDS`` shortcut,
  and ``finally: broker_service.close()`` shutdown path.
* Catches import-time and module-load regressions that an in-process
  test would miss because pytest already imported everything.
* Each test runs in its own ``tmp_path`` so cache, journal, and
  DuckDB writes never touch the real ``runtime-dev/`` tree.
"""

from __future__ import annotations

import pytest

from interface.ui.tests.endpoint_manifest import (
    LIVE_READONLY_ENDPOINTS,
    OFFLINE_ENDPOINTS,
    SANDBOX_ENDPOINTS,
)

# ── offline matrix (default CI) ───────────────────────────────────────


@pytest.mark.cli_endpoint
@pytest.mark.parametrize(
    "endpoint",
    OFFLINE_ENDPOINTS,
    ids=lambda e: e.id,
)
def test_cli_endpoint_offline(run_cli, endpoint):
    result = run_cli(endpoint.argv, timeout=endpoint.timeout_s)
    assert not result.timeout, f"endpoint {endpoint.id!r} timed out after {endpoint.timeout_s}s"
    assert result.returncode == endpoint.expect_exit, (
        f"{endpoint.id!r}: expected exit {endpoint.expect_exit}, got {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    if endpoint.expect_stdout_substr:
        combined = result.stdout + result.stderr
        assert endpoint.expect_stdout_substr in combined, (
            f"{endpoint.id!r}: expected substring {endpoint.expect_stdout_substr!r} "
            f"in output\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )


# ── live_readonly matrix (auto-skip when creds missing) ──────────────


@pytest.mark.cli_endpoint
@pytest.mark.cli_endpoint_live
@pytest.mark.parametrize(
    "endpoint",
    [e for e in LIVE_READONLY_ENDPOINTS if not e.no_subprocess],
    ids=lambda e: e.id,
)
def test_cli_endpoint_live_readonly(run_cli, endpoint):
    result = run_cli(endpoint.argv, timeout=endpoint.timeout_s)
    assert not result.timeout, f"endpoint {endpoint.id!r} timed out after {endpoint.timeout_s}s"
    assert result.returncode == endpoint.expect_exit, (
        f"{endpoint.id!r}: expected exit {endpoint.expect_exit}, got {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


# ── global flag smoke (offline subset) ────────────────────────────────


@pytest.mark.cli_endpoint
def test_flag_json_help_outputs_json(run_cli):
    """`--json` on the help command should produce parseable JSON."""
    import json

    result = run_cli(["--json", "help"], timeout=15)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload.get("help") is True
    assert "commands" in payload and isinstance(payload["commands"], list)


@pytest.mark.cli_endpoint
def test_flag_verbose_does_not_crash(run_cli):
    result = run_cli(["--verbose", "help"], timeout=15)
    assert result.returncode == 0


@pytest.mark.cli_endpoint
def test_flag_timing_does_not_crash(run_cli):
    result = run_cli(["--timing", "help"], timeout=15)
    assert result.returncode == 0


@pytest.mark.cli_endpoint
def test_flag_broker_invalid_exits_1(run_cli):
    result = run_cli(["--broker", "not-a-broker", "doctor"], timeout=20)
    assert result.returncode == 1
    assert "broker" in (result.stdout + result.stderr).lower()


# ── dispatcher invariants ─────────────────────────────────────────────


@pytest.mark.cli_endpoint
def test_unknown_command_exits_1_with_message(run_cli):
    result = run_cli(["nope-not-a-cmd"], timeout=10)
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "Unknown command" in combined


@pytest.mark.cli_endpoint
def test_help_subcommand_matches_no_args(run_cli):
    """`help` and bare invocation must be equivalent."""
    a = run_cli(["help"], timeout=10)
    b = run_cli([], timeout=10)
    assert a.returncode == b.returncode == 0
    assert "TradeXV2 CLI" in a.stdout
    assert "TradeXV2 CLI" in b.stdout


# ── negative: every manifest tier has at least one entry ─────────────


def test_manifest_tiers_nonempty():
    """Catches accidental emptying of a tier during refactors."""
    assert len(OFFLINE_ENDPOINTS) >= 15, "offline tier shrunk — review"
    assert len(LIVE_READONLY_ENDPOINTS) >= 10, "live_readonly tier shrunk"
    assert len(SANDBOX_ENDPOINTS) >= 1, "sandbox tier empty"


# ── sandbox endpoints are only run when explicitly opted in ───────────


def test_sandbox_endpoints_are_gated():
    """Sandbox endpoints must never run in default CI.

    This test enforces the rule: a sandbox endpoint must declare the
    ``sandbox`` tier, which the conftest gates behind
    ``DHAN_INTEGRATION=1``.  Adding a sandbox endpoint to a different
    tier is a bug.
    """
    for ep in SANDBOX_ENDPOINTS:
        assert ep.tier == "sandbox", f"{ep.id!r} is in SANDBOX list but tier={ep.tier!r}"
