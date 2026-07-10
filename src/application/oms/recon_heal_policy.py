"""Reconciliation heal policy — correct-then-heal, human-gated by default.

Safe-to-trade gate (Phase 1 / P0-H companion)
--------------------------------------------
Reconciliation always **detects** drift. **Repair** of local OMS state from
broker truth is opt-in so an operator (or automated SRE) must explicitly
enable heal mode — never silent self-heal in production by default.

Policy
------
* ``report_only`` (default) — surface drift; never mutate OMS.
* ``heal`` — when ``TRADEX_RECONCILIATION_AUTO_REPAIR=1``, apply
  **correct-then-heal** for HIGH-severity items only (missing local
  orders/positions, quantity mismatches). MEDIUM status mismatches are
  reported but not auto-healed unless the adapter opts in.

Heal is always **local OMS catches up to broker** (broker is authoritative).
It never sends cancel/place to the broker.

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

# Drift kinds that are safe to auto-heal (broker wins → local OMS).
HEALABLE_KINDS: frozenset[str] = frozenset(
    {
        "missing_local_order",
        "missing_local_position",
        "position_quantity_mismatch",
        "funds_mismatch",  # informational; adapters may only log
    }
)


class HealMode(str, Enum):
    """Reconciliation heal mode."""

    REPORT_ONLY = "report_only"
    HEAL = "heal"


def resolve_heal_mode(*, env: dict[str, str] | None = None) -> HealMode:
    """Resolve heal mode from environment (or *env* mapping for tests)."""
    source = env if env is not None else os.environ
    raw = (source.get(ENV_AUTO_REPAIR) or "").strip()
    if raw == "1":
        return HealMode.HEAL
    return HealMode.REPORT_ONLY


def should_auto_repair(*, env: dict[str, str] | None = None) -> bool:
    """True when adapters should run local OMS repair after drift detection."""
    return resolve_heal_mode(env=env) is HealMode.HEAL


def is_healable_kind(kind: str) -> bool:
    """Return True if *kind* is eligible for auto-heal under correct-then-heal."""
    return kind in HEALABLE_KINDS


def log_heal_mode() -> HealMode:
    """Log and return the active heal mode (call once at composition root)."""
    mode = resolve_heal_mode()
    if mode is HealMode.HEAL:
        logger.warning(
            "reconciliation_heal_mode=heal "
            "(%s=1) — local OMS will be repaired from broker for HIGH healable drift",
            ENV_AUTO_REPAIR,
        )
    else:
        logger.info(
            "reconciliation_heal_mode=report_only "
            "(set %s=1 to enable correct-then-heal)",
            ENV_AUTO_REPAIR,
        )
    return mode
