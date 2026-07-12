"""Broker mode resolution helpers for ``tradex.open_session``.

Extracted from ``tradex.session``. Resolves the effective connect mode and
whether a broker is "live", using the broker plugin registry rather than any
concrete broker import.
"""

from __future__ import annotations

from typing import Any

from domain.connect_errors import ConnectError, UNKNOWN_MODE
from domain.session_status import (
    MODE_MARKET,
    MODE_SIM,
    MODE_TRADE,
    VALID_MODES,
)
from infrastructure.broker_plugin import ensure_core_plugins, get_broker_plugin


def default_mode(broker_id: str) -> str:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    if plugin is not None:
        return plugin.default_mode
    if broker_id == "paper":
        return MODE_SIM
    return MODE_MARKET


def is_live(broker_id: str) -> bool:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    if plugin is not None:
        return plugin.is_live
    return broker_id in {"dhan", "upstox"}


def normalize_mode(broker_id: str, mode: str | None) -> str:
    ensure_core_plugins()
    plugin = get_broker_plugin(broker_id)
    resolved = (mode or default_mode(broker_id)).lower().strip()
    if resolved not in VALID_MODES:
        raise ConnectError(
            f"Unknown connect mode {mode!r}.",
            code=UNKNOWN_MODE,
            broker_id=broker_id,
            mode=str(mode or ""),
            remediation=f"Use one of: {', '.join(sorted(VALID_MODES))}.",
        )
    if plugin is not None:
        # Paper: market/trade alias to sim
        if broker_id == "paper" and resolved in {MODE_MARKET, MODE_TRADE}:
            return MODE_SIM
        if resolved not in plugin.supported_modes and broker_id != "paper":
            if resolved == MODE_SIM and plugin.is_live:
                raise ConnectError(
                    f"mode='sim' is only valid for paper.",
                    code=UNKNOWN_MODE,
                    broker_id=broker_id,
                    mode=resolved,
                    remediation="Use mode='market' (data) or mode='trade' (OMS).",
                )
    else:
        if broker_id == "paper" and resolved in {MODE_MARKET, MODE_TRADE}:
            return MODE_SIM
        if is_live(broker_id) and resolved == MODE_SIM:
            raise ConnectError(
                f"mode='sim' is only valid for paper.",
                code=UNKNOWN_MODE,
                broker_id=broker_id,
                mode=resolved,
                remediation="Use mode='market' (data) or mode='trade' (OMS).",
            )
    return resolved
