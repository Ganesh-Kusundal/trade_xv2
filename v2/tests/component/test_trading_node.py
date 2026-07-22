"""TradingNode — configure paper profile + start/stop."""

from __future__ import annotations

from pathlib import Path

from tradex.node import TradingNode

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def test_configure_paper_start_stop() -> None:
    node = TradingNode()
    node.configure(str(_CONFIG_DIR), profile="paper")
    node.start()
    assert node.runtime is not None
    assert node.runtime.environment_frozen is True
    node.stop()
