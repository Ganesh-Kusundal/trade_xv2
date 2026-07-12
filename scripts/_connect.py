"""Shared broker connect helpers for scripts — standard bootstrap path only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure src/ is on path when scripts run from repo root.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def bootstrap_or_exit(
    broker: str,
    *,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    **kwargs: Any,
) -> Any:
    """Live connect via require_gateway; exit 1 on failure."""
    from infrastructure.gateway.factory import require_gateway

    try:
        return require_gateway(
            broker,
            env_path=env_path,
            load_instruments=load_instruments,
            **kwargs,
        )
    except Exception as exc:
        print(f"ERROR: bootstrap failed for {broker!r}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def bootstrap_or_none(
    broker: str,
    *,
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    **kwargs: Any,
) -> Any | None:
    """Live connect; return None instead of exiting."""
    try:
        return bootstrap_or_exit(
            broker,
            env_path=env_path,
            load_instruments=load_instruments,
            **kwargs,
        )
    except SystemExit:
        return None
