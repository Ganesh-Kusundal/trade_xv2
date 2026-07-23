"""Broker-extension registry — broker-unique capabilities without protocol bloat.

The shared ``BrokerAdapter`` protocol only covers what every venue can do.
Features only one broker has (Dhan super orders/forever orders/EDIS, an
Upstox-only endpoint, ...) don't belong on that protocol, and shouldn't be
special-cased in application code either. Each gateway instead owns a
``BrokerExtensions`` registry; broker-unique features register themselves as
plain objects and callers look them up by type via ``gateway.extension(...)``
— mirrors legacy's ``BrokerSession.extension(ext_type)`` lookup, adapted to
v2's gateway-is-the-session shape (v2 has no separate session wrapper).

No concrete extension ships in this module — it is the seam, not a feature.
The first broker-unique capability that needs one registers a plain object
through this registry instead of widening ``BrokerAdapter`` or branching on
broker id in application code. (As of this pass, Dhan registers
``DhanDepth20Extension`` / ``DhanDepth200Extension`` on its gateway; Upstox
registers none yet because its depth streaming path is not implemented.)
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


class BrokerExtensions:
    """Per-gateway registry of broker-specific extension objects."""

    def __init__(self, *extensions: Any) -> None:
        self._extensions: list[Any] = list(extensions)

    def register(self, extension: Any) -> Any:
        self._extensions.append(extension)
        return extension

    def get(self, ext_type: type[T]) -> T:
        """Return the registered extension matching ``ext_type``.

        Raises
        ------
        LookupError
            If no matching extension is registered on this gateway.
        """
        for ext in self._extensions:
            if isinstance(ext, ext_type):
                return ext
        available = [type(e).__name__ for e in self._extensions] or ["none"]
        raise LookupError(f"Extension {ext_type!r} not registered. Available: {available}")

    def names(self) -> list[str]:
        return [type(e).__name__ for e in self._extensions]
