"""Canonical connection — readiness probes, bootstrap results, typed errors."""
from infrastructure.connection.authenticated_readiness import *  # noqa: F401
from infrastructure.connection.bootstrap_result import *  # noqa: F401
from infrastructure.connection.errors import *  # noqa: F401

__all__ = [
    "AuthProbeResult",
    "BootstrapResult",
    "BootstrapStatus",
    "BrokerNotReadyError",
    "authenticated_readiness_probe",
    "classify_exception",
    "execute_read_only_probe",
    "is_token_rejection",
    "is_token_rejection_from_result",
    "structural_readiness_probe",
]
