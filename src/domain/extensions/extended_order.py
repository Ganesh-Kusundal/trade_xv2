"""Synchronous capability port for broker-specific extended order types.

``ExtendedOrderExecutor`` is the single extension interface that
``application.oms.ExtendedOrderService`` resolves through
``BrokerExtensionRegistry.require(broker_id, ExtendedOrderExecutor)``.

It exists so the OMS never branches on broker **name** strings
(``if broker == "dhan"``) nor probes gateway internals
(``getattr(gw, "_broker")`` / ``"_conn"``): every broker-specific execution
detail for super / forever / trigger / gtt / cover / slice / exit-all /
kill-switch lives inside the broker's own implementation of this port.

Adding a new broker means implementing this port (only for the operations it
supports) and registering it in the broker's ``ExtensionBundle`` — **zero edits
to the OMS**.

Contract:
    * Methods take the raw request ``payload`` (a plain dict as received from the
      API/UI surface) and return the raw broker response object, unchanged.
    * The OMS layer owns kill-switch, pre-trade risk, ``oms_managed`` and event
      publishing — implementations MUST NOT re-implement those concerns.
    * Operations a broker does not support are left to the default
      implementation here, which raises :class:`UnsupportedExtensionError`.
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from domain.exceptions import UnsupportedExtensionError


class ExtendedOrderExecutor(ABC):
    """Broker-specific executor for extended order types (sync, payload-based).

    Subclasses override only the operations their broker supports. The base
    implementations raise :class:`UnsupportedExtensionError`, so an unsupported
    operation surfaces a clear, broker-attributed error rather than a silent
    no-op or a name-branch in the OMS.

    Subclasses should set :attr:`broker_id` so error messages attribute the
    unsupported feature to the correct broker.
    """

    #: Broker this executor belongs to; used in unsupported-feature errors.
    broker_id: str = "unknown"

    def _unsupported(self, feature: str) -> UnsupportedExtensionError:
        return UnsupportedExtensionError(
            broker_id=self.broker_id,
            extension_name=feature,
        )

    def place_super_order(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("super orders")

    def place_forever_order(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("forever orders")

    def place_trigger(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("conditional triggers")

    def exit_all(self) -> Any:
        raise self._unsupported("exit-all")

    def place_gtt(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("GTT orders")

    def place_cover_order(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("cover orders")

    def place_slice_order(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("slice orders")

    def set_kill_switch(self, payload: dict[str, Any]) -> Any:
        raise self._unsupported("kill switch")


__all__ = ["ExtendedOrderExecutor"]
