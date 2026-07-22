"""E2E: TradingNode paper session configure → start → stop (real components)."""

from __future__ import annotations

from pathlib import Path

from tradex.node import TradingNode

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_paper_session_configure_start_stop() -> None:
    node = TradingNode()
    node.configure(str(_CONFIG_DIR), profile="paper")
    runtime = node.start()
    assert runtime is not None
    assert runtime.environment_frozen is True
    assert node.runtime is runtime
    node.stop()
