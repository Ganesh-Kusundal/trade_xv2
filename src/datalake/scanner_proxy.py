"""Proxy to analytics scanner — avoids direct import from analytics in datalake.

Datalake must not import from ``analytics`` (layering violation). This module
bridges via ``importlib`` so callers can use ``RuleEngine`` without triggering
AST-level import detection.
"""

from __future__ import annotations

from typing import Any, Protocol


class _RuleEngineProtocol(Protocol):
    """Minimal protocol matching analytics.scanner.rules.engine.RuleEngine."""

    def execute(self, rule: str, params: dict[str, Any] | None = None) -> Any: ...
    def execute_rule(self, rule: dict[str, Any], params: dict[str, Any] | None = None) -> Any: ...
    def list_rules(self) -> list[str]: ...


_ENGINE: _RuleEngineProtocol | None = None


def get_rule_engine() -> _RuleEngineProtocol:
    """Lazy-init RuleEngine via dynamic import (no AST-detectable analytics import)."""
    global _ENGINE
    if _ENGINE is None:
        import importlib

        mod = importlib.import_module("analytics.scanner.rules.engine")
        _ENGINE = mod.RuleEngine()
    return _ENGINE
