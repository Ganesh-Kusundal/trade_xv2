"""Backward-compat shim — canonical implementation is in application.services.reconciliation_service."""

from application.services.reconciliation_service import (  # noqa: F401
    ReconciliationEngine,
)

__all__ = ["ReconciliationEngine"]
