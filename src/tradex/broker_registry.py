"""Ensure a broker package self-registers its adapters (composition root).

Extracted from ``tradex.session``. Routes through the composition root's
entry-point discovery (``runtime.broker_discovery``) rather than naming a
concrete broker module, so no layer above ``infrastructure``/``brokers``
imports a broker by name.
"""

from __future__ import annotations


def ensure_registered(broker_id: str) -> None:
    """Import broker package so self-registration runs."""
    if broker_id in ("datalake",):
        return
    from runtime.broker_discovery import ensure_broker_module

    ensure_broker_module(broker_id)
