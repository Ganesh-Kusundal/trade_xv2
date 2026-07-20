"""Validate that a broker gateway's declared capabilities match its methods.

A ``BrokerCapabilities``-like object advertises what a broker can do via
``supports_*`` boolean flags. This module cross-checks those flags against the
methods that actually exist on the gateway object, so a misconfigured
capability matrix (e.g. ``supports_modify_order=True`` but no ``modify_order``
method) is surfaced as a WARNING instead of failing later at call time.
"""

import logging
from typing import Any

from domain.errors import CapabilityError

# Maps a capability flag to the method name(s) that must exist on the gateway
# when the flag is True. The first name present on the gateway satisfies the
# capability, so multiple acceptable aliases can be listed.
_CAPABILITY_METHOD_MAP: dict[str, tuple[str, ...]] = {
    "supports_modify_order": ("modify_order",),
    "supports_cancel_order": ("cancel_order",),
    "supports_order_stream": ("stream_order",),
    "supports_depth": ("depth", "stream_depth"),
}

# Deprecated alias — use domain.errors.CapabilityError
CapabilityMismatchError = CapabilityError


def validate_gateway_capabilities(
    gateway: Any,
    log: logging.Logger = logging.getLogger(__name__),
) -> list[str]:
    """Check a gateway's capabilities against the methods it actually exposes.

    Pure check, never raises — existing callers rely on this returning a
    plain list. Use :func:`enforce_gateway_capabilities` at gateway
    construction time when a mismatch must abort startup.

    Args:
        gateway: Object exposing a ``capabilities()`` method returning a
            ``BrokerCapabilities``-like object with ``supports_*`` attributes.
        log: Logger used to emit WARNINGs for each detected mismatch.

    Returns:
        A list of human-readable mismatch strings (empty when consistent).
    """
    capabilities = gateway.capabilities()
    mismatches: list[str] = []

    for capability, method_names in _CAPABILITY_METHOD_MAP.items():
        supported = getattr(capabilities, capability, False)
        if not supported:
            continue

        if all(getattr(gateway, name, None) is None for name in method_names):
            message = (
                f"Capability {capability}=True but gateway "
                f"{type(gateway).__name__!r} has none of the expected methods "
                f"{list(method_names)}"
            )
            log.warning(message)
            mismatches.append(message)

    return mismatches


def enforce_gateway_capabilities(
    gateway: Any,
    log: logging.Logger = logging.getLogger(__name__),
) -> None:
    """Run :func:`validate_gateway_capabilities` and abort on any mismatch.

    Call this from a gateway's ``__init__`` (in place of the bare check) so
    a capability lie fails startup instead of only being logged. This
    closes the gap between the already-correct check and the
    already-specified but previously-unenforced startup invariant
    ("capability lie → abort or strip") in
    docs/architecture/TARGET_SYSTEM_DESIGN.md §6.

    Raises:
        CapabilityError: if any advertised capability has no backing method on the gateway.
    """
    mismatches = validate_gateway_capabilities(gateway, log=log)
    if mismatches:
        raise CapabilityError(
            f"{type(gateway).__name__} advertises capabilities it cannot "
            f"deliver: {'; '.join(mismatches)}"
        )
