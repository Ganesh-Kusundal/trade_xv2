"""CheckStrategy protocol and CheckResult model for doctor diagnostics.

This module defines the Strategy pattern interface for diagnostic checks.
Each check implements CheckStrategy and returns a list of CheckResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService


@dataclass
class CheckResult:
    """Single diagnostic check result.

    Attributes
    ----------
    name : str
        Human-readable name of the check (e.g., "Quote", "Active Broker").
    status : str
        One of "PASS", "WARN", "FAIL", "INFO", "ERROR".
    detail : str
        Additional context or error message.
    """

    name: str
    status: str
    detail: str = ""


class CheckStrategy(Protocol):
    """Protocol for diagnostic check strategies.

    Every check strategy implements this protocol, allowing the
    CheckOrchestrator to run them polymorphically.

    Example
    -------
    >>> class MyCheck:
    ...     def execute(self, broker_service) -> list[CheckResult]:
    ...         return [CheckResult("My Check", "PASS", "OK")]
    """

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Execute the diagnostic check.

        Parameters
        ----------
        broker_service : BrokerService | None
            The active broker service instance. May be None for checks
            that don't require a broker (e.g., BrokerRegistryCheck).

        Returns
        -------
        list[CheckResult]
            One or more check results. Never raises — exceptions are
            caught and converted to FAIL/ERROR results.
        """
        ...
