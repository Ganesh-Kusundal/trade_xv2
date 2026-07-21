"""Canonical connection — readiness probes, bootstrap results, typed errors."""

from domain.exceptions import BrokerNotReadyError
from infrastructure.connection.authenticated_readiness import (
    AuthProbeResult,
    authenticated_readiness_probe,
    execute_read_only_probe,
    is_token_rejection,
    is_token_rejection_from_result,
)
from infrastructure.connection.bootstrap_result import (
    BootstrapResult,
    BootstrapStatus,
    classify_exception,
    structural_readiness_probe,
)

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
