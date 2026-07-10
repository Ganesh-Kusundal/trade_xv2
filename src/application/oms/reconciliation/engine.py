"""Thin re-export — canonical home is ``domain.reconciliation_engine``.

Kept for backward compatibility with
``application.oms.reconciliation.engine`` import paths.
"""

from __future__ import annotations

from domain.reconciliation_engine import ReconciliationEngine

__all__ = ["ReconciliationEngine"]
