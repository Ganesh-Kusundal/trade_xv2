"""Parity enforcement configuration and CI helpers.

This module ensures that parity tests are mandatory and enforced.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Parity enforcement flag - when True, all parity tests must pass
ENFORCE_PARITY = os.getenv("ENFORCE_PARITY", "1") == "1"

# Strict execution parity - requires identical results across modes
STRICT_EXECUTION_PARITY = os.getenv("STRICT_EXECUTION_PARITY", "1") == "1"


def parity_required() -> bool:
    """Return True if parity tests are mandatory."""
    return ENFORCE_PARITY


def strict_parity_required() -> bool:
    """Return True if strict execution parity is enforced."""
    return STRICT_EXECUTION_PARITY


def check_parity_environment() -> None:
    """Validate that parity test dependencies are available.

    Raises SystemExit if required dependencies are missing when parity is enforced.
    """
    if not parity_required():
        return

    # Check for required test dependencies
    missing = []
    try:
        import hypothesis
    except ImportError:
        missing.append("hypothesis")

    if missing and parity_required():
        print(
            f"ERROR: Parity enforcement requires: {', '.join(missing)}\n"
            f"Install with: pip install {' '.join(missing)}\n"
            f"Or disable parity: ENFORCE_PARITY=0 pytest ..."
        )
        sys.exit(1)


# Parity test markers for pytest
PARITY_MARKERS = {
    "paper_replay_parity": "Paper trading ↔ Replay engine parity",
    "cross_broker_parity": "Cross-broker data source parity",
    "live_backtest_parity": "Live ↔ Backtest execution parity",
    "scanner_determinism": "Scanner output determinism",
    "feature_parity": "Feature computation parity across runs",
}


def register_parity_markers(config):
    """Register parity test markers with pytest."""
    for marker_name, description in PARITY_MARKERS.items():
        config.addinivalue_line(
            "markers", f"{marker_name}: {description}"
        )
