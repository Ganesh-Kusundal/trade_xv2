"""Backward-compat shim — canonical implementation is in application.services.simulation_orchestrator."""

from application.services.simulation_orchestrator import (  # noqa: F401
    PortfolioProjector,
    project_trade,
)

__all__ = ["PortfolioProjector", "project_trade"]
