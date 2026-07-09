"""Broker capability facade — exposes broker-specific methods on an Instrument.

``Instrument.broker`` returns one of these.  It aggregates every extension
registered for the instrument's broker and forwards attribute access to the
first extension that implements the requested capability, so::

    instrument.broker.depth200()   # -> DhanDepth200Extension.depth200()
    instrument.broker.depth20()    # -> DhanDepth20Extension.depth20()
    instrument.broker.depth30()    # -> UpstoxDepth30Extension.depth30()

The domain layer (and user code) never imports broker-specific types directly;
it only calls capability-named methods through this facade.
"""

from __future__ import annotations

from typing import Any


class BrokerFacade:
    """Read-only view over a broker's extensions, resolved by capability name."""

    def __init__(self, broker_id: str, extensions: list[Any]) -> None:
        object.__setattr__(self, "_broker_id", broker_id)
        object.__setattr__(self, "_exts", list(extensions))

    @property
    def broker_id(self) -> str:
        return self._broker_id

    def _resolve(self, name: str) -> Any:
        for ext in self._exts:
            if hasattr(ext, name):
                return getattr(ext, name)
        raise AttributeError(
            f"broker {self._broker_id!r} has no capability named {name!r}"
        )

    def __getattr__(self, name: str) -> Any:
        # Only invoked when normal attribute lookup fails (e.g. depth200).
        return object.__getattribute__(self, "_resolve")(name)

    def __repr__(self) -> str:
        names = [getattr(e, "name", type(e).__name__) for e in self._exts]
        return f"BrokerFacade(broker={self._broker_id!r}, extensions={names})"
