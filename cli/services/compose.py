"""Composition root — single entry point for wiring the trading runtime.

Delegates to :mod:`runtime.trading_runtime_factory` for unified bootstrap.
"""

from __future__ import annotations

from pathlib import Path

from runtime.trading_runtime_factory import Runtime, build_runtime as _factory_build


def build_runtime(
    broker: str = "dhan",
    *,
    authorize_risk_fail_open: bool = False,
    env_path: Path | None = None,
) -> Runtime:
    """Single composition root for the trading runtime."""
    return _factory_build(
        broker=broker,
        authorize_risk_fail_open=authorize_risk_fail_open,
        env_path=env_path,
        skip_parity_gate=True,
    )


__all__ = ["Runtime", "build_runtime"]
