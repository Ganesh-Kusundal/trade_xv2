"""Runtime parity gate — refuse live boot if quant determinism checks fail."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def assert_runtime_parity_or_raise() -> None:
    """Run parity verifiers; raise RuntimeError if checks fail.

    Skipped when ``SKIP_PARITY_GATE=1`` (local dev / tests).
    LIVE environments (``TRADEX_ENV`` = ``production`` or ``staging``)
    **must not** honour ``SKIP_PARITY_GATE`` — the gate always runs.
    """
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    is_live_env = env in ("production", "staging")

    if not is_live_env and os.getenv("SKIP_PARITY_GATE", "0") == "1":
        logger.debug("parity_gate: skipped (SKIP_PARITY_GATE=1, env=%s)", env)
        return

    if not is_live_env and os.getenv("PYTEST_CURRENT_TEST"):
        return

    failures: list[str] = []

    replay_test = _PROJECT_ROOT / "tests" / "integration" / "test_event_replay_determinism.py"
    if replay_test.exists():
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_PROJECT_ROOT / "src")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(replay_test),
                "-q",
                "--tb=short",
            ],
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            failures.append(f"event_replay_verifier: {result.stderr or result.stdout}")

    quant_script = _PROJECT_ROOT / "scripts" / "verify" / "baseline_quant_parity.py"
    if quant_script.exists():
        result = subprocess.run(
            [sys.executable, str(quant_script), "--mode", "verify"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            failures.append(f"quant_parity_baseline: {result.stderr or result.stdout}")

    shadow_test = (
        _PROJECT_ROOT / "tests" / "architecture" / "test_shadow_parity_gate.py"
    )
    if shadow_test.exists():
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_PROJECT_ROOT / "src")
        env["TRADEX_LEDGER_AUTHORITY"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(shadow_test),
                "-q",
                "--tb=short",
            ],
            cwd=_PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            failures.append(f"shadow_parity_gate: {result.stderr or result.stdout}")

    if failures:
        msg = "Runtime parity gate failed:\n" + "\n".join(failures)
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Runtime parity gate passed")
