"""TradingNode — public composition-root wrapper."""

from __future__ import annotations

from typing import Any

from config.loader import load_config
from runtime.discovery import discover_brokers
from runtime.factory import RuntimeFactory
from runtime.startup import boot


class TradingNode:
    """configure → start → stop (+ optional submit)."""

    def __init__(self) -> None:
        self._runtime: Any | None = None
        self._config: Any | None = None

    @property
    def runtime(self) -> Any | None:
        return self._runtime

    def configure(self, config_dir: str, profile: str = "paper") -> None:
        cfg = load_config(config_dir, profile=profile)
        discover_brokers()
        self._config = cfg
        self._runtime = RuntimeFactory.build(cfg)

    def start(self) -> Any:
        if self._runtime is None:
            raise RuntimeError("TradingNode not configured")
        self._runtime = boot(self._runtime)
        return self._runtime

    def stop(self) -> None:
        if self._runtime is not None:
            self._runtime.lifecycle.stop_all()

    def submit(self, command: Any) -> Any:
        if self._runtime is None:
            raise RuntimeError("TradingNode not configured")
        return self._runtime.execution_engine.submit(command)
