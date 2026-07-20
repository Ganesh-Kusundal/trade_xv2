"""Reconciliation heal policy — correct-then-heal; heal on by default for live (F4).

Safe-to-trade gate (Phase 1 / P0-H companion)
--------------------------------------------
Reconciliation always **detects** drift. **Repair** of local OMS state from
broker truth defaults to **on** for live safety (F4). Operators can force
report-only with ``TRADEX_RECONCILIATION_AUTO_REPAIR=0``.

Policy
------
* ``heal`` (default) — apply correct-then-heal for HIGH-severity items
  (missing local orders/positions, quantity mismatches).
* ``report_only`` — when ``TRADEX_RECONCILIATION_AUTO_REPAIR=0``, surface
  drift; never mutate OMS via broker adapters.

Heal is always **local OMS catches up to broker** (broker is authoritative).
It never sends cancel/place to the broker. ``ExecutionEngine.apply_mass_status``
always upserts; this flag gates broker-adapter ``auto_repair`` paths.

Usage
-----
    from application.oms.recon_heal_policy import should_auto_repair, HealMode

    recon = DhanReconciliationService(..., auto_repair=should_auto_repair())
"""

from __future__ import annotations

import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)

# Env flag — documented in .env.example / SAFE_TO_TRADE_GATE.md
ENV_AUTO_REPAIR = "TRADEX_RECONCILIATION_AUTO_REPAIR"


class HealMode(str, Enum):
    """Reconciliation heal mode."""

    REPORT_ONLY = "report_only"
    HEAL = "heal"


def resolve_heal_mode(*, env: dict[str, str] | None = None) -> HealMode:
    """Resolve heal mode from environment (or *env* mapping for tests).

    Default is HEAL (F4 live safety). Set ``TRADEX_RECONCILIATION_AUTO_REPAIR=0``
    for report-only.
    """
    source = env if env is not None else os.environ
    raw = (source.get(ENV_AUTO_REPAIR) if ENV_AUTO_REPAIR in source else "1") or "1"
    raw = str(raw).strip().lower()
    if raw in ("0", "false", "no", "off", "report_only"):
        return HealMode.REPORT_ONLY
    return HealMode.HEAL


def should_auto_repair(*, env: dict[str, str] | None = None) -> bool:
    """True when adapters should run local OMS repair after drift detection."""
    return resolve_heal_mode(env=env) is HealMode.HEAL


def log_heal_mode() -> HealMode:
    """Log and return the active heal mode (call once at composition root)."""
    mode = resolve_heal_mode()
    if mode is HealMode.HEAL:
        logger.warning(
            "reconciliation_heal_mode=heal "
            "(default; set %s=0 for report-only) — local OMS repaired from broker",
            ENV_AUTO_REPAIR,
        )
    else:
        logger.info(
            "reconciliation_heal_mode=report_only (%s=0) — drift reported, not auto-healed",
            ENV_AUTO_REPAIR,
        )
    return mode
