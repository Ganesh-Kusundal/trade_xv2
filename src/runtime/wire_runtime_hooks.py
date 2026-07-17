"""Shared composition-root wiring for domain runtime hooks.

Analytics engines (backtest / replay / paper) obtain the OMS trading context
and backtest adapter through ``domain.runtime_hooks`` accessors rather than
importing ``application.oms`` / ``application.execution`` directly (D2 inverse
import-linter contract). Every entrypoint that can drive a PARITY path must
call :func:`wire_runtime_hooks` once before constructing engines, otherwise
the hook accessors raise ``RuntimeError``.

This single function replaces the duplicated registration blocks previously
scattered across ``src/interface/api/main.py`` and ``tests/conftest.py``.
"""

from __future__ import annotations

from domain.events import DomainEvent
from domain.runtime_hooks import (
    register_domain_event_factory,
    register_oms_backtest_factory,
    register_trading_context_factory,
)

_wired = False


def wire_runtime_hooks() -> None:
    """Register the real factories into ``domain.runtime_hooks`` (idempotent).

    Registers the constructors themselves — never the hook accessors, which
    would recurse into themselves.
    """
    global _wired
    if _wired:
        return

    from application.execution.factory import create_oms_backtest_adapter
    from application.oms.factory import create_trading_context

    register_oms_backtest_factory(create_oms_backtest_adapter)
    # Real constructor only — registering runtime_hooks.create_domain_event
    # would recurse (hook accessor -> registered factory -> same accessor).
    register_domain_event_factory(DomainEvent.now)
    register_trading_context_factory(create_trading_context)

    _wired = True


def reset_wire_runtime_hooks() -> None:
    """Test helper: allow re-wiring in a fresh process."""
    global _wired
    _wired = False
