"""Backward-compat facade — canonical: runtime.broker_infrastructure.

Composition root lives under ``runtime/`` (allowed to wire application layers).
Prefer::

    from runtime.broker_infrastructure import BrokerInfrastructure, build_infrastructure
"""
from runtime.broker_infrastructure import BrokerInfrastructure, build_infrastructure  # noqa: F401

__all__ = ["BrokerInfrastructure", "build_infrastructure"]
