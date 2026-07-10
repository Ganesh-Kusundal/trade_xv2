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
    """
    if os.getenv("SKIP_PARITY_GATE", "0") == "1":
        logger.debug("parity_gate: skipped (SKIP_PARITY_GATE=1)")
        return

    if os.getenv("PYTEST_CURRENT_TEST"):
        return

    failures: list[str] = []

    replay_script = _PROJECT_ROOT / "scripts" / "verify_event_replay.py"
    if replay_script.exists():
        result = subprocess.run(
            [sys.executable, "-m", "scripts.verify_event_replay"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            failures.append(f"event_replay_verifier: {result.stderr or result.stdout}")

    quant_script = _PROJECT_ROOT / "scripts" / "baseline_quant_parity.py"
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

    if failures:
        msg = "Runtime parity gate failed:\n" + "\n".join(failures)
        logger.error(msg)
        raise RuntimeError(msg)

    logger.info("Runtime parity gate passed")
