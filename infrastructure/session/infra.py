"""Backward-compat facade — canonical: runtime.session_infra.

Composition root lives under ``runtime/`` (allowed to wire application layers).
Prefer::

    from runtime.session_infra import wire_gateway_for_session, SessionKernel
"""
from runtime.session_infra import *  # noqa: F403
from runtime.session_infra import (
    SessionKernel,
    get_session_quota_scheduler,
    get_session_registry,
    wire_gateway_for_session,
)

__all__ = [
    "SessionKernel",
    "get_session_quota_scheduler",
    "get_session_registry",
    "wire_gateway_for_session",
]
