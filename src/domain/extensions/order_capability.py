"""Capability port for broker-specific extended order types (DR-B1).

``OrderCapabilityPort`` is the *interface* the OMS depends on for super /
forever / trigger / gtt / cover / slice / exit-all / kill-switch execution.
It is a structural (``runtime_checkable``) Protocol so any broker adapter that
implements the method set satisfies it — the OMS never imports a concrete
broker class to use it.

Why a Protocol and not ``if broker == "dhan"``
------------------------------------------------
The OMS resolves an implementation through
``BrokerExtensionRegistry.require(broker_id, OrderCapabilityPort)`` (see
:mod:`domain.extensions.broker_bundle`).  The registry answers the question
*“does this broker declare an implementation of the extended-order
capability?”* — never *“are you broker Y?”*.  A broker that does not register
the capability raises :class:`domain.errors.UnsupportedExtensionError`, which
the OMS turns into a clear, broker-attributed rejection.

Adding a broker therefore means implementing this port (only for the
operations it supports) and registering it in the broker's
``ExtensionBundle`` — **zero edits to the OMS**.

Contract
--------
* Methods take the raw request ``payload`` (a plain dict as received from the
  API/UI surface) and return the raw broker response object, unchanged.
* The OMS layer owns kill-switch, pre-trade risk, ``oms_managed`` and event
  publishing — implementations MUST NOT re-implement those concerns.
* Operations a broker does not support are left to the default implementation
  (in :class:`domain.extensions.extended_order.ExtendedOrderExecutor`), which
  raises :class:`domain.errors.UnsupportedExtensionError`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OrderCapabilityPort(Protocol):
    """Broker-specific executor for extended order types (sync, payload-based).

    ``domain.extensions.extended_order.ExtendedOrderExecutor`` is the concrete
    ABC that broker adapters subclass; it is structurally compatible with this
    Protocol, so ``registry.require(broker_id, OrderCapabilityPort)`` accepts it.
    """

    #: Broker this executor belongs to; used in unsupported-feature errors.
    broker_id: str

    def place_super_order(self, payload: dict[str, Any]) -> Any:
        """Place a super (bracket) order. Raises if unsupported."""
        ...

    def place_forever_order(self, payload: dict[str, Any]) -> Any:
        """Place a forever (GTT-style persistent) order. Raises if unsupported."""
        ...

    def place_trigger(self, payload: dict[str, Any]) -> Any:
        """Place a conditional trigger order. Raises if unsupported."""
        ...

    def exit_all(self) -> Any:
        """Flatten all positions. Raises if unsupported."""
        ...

    def place_gtt(self, payload: dict[str, Any]) -> Any:
        """Place a Good-Till-Triggered order. Raises if unsupported."""
        ...

    def place_cover_order(self, payload: dict[str, Any]) -> Any:
        """Place a cover order. Raises if unsupported."""
        ...

    def place_slice_order(self, payload: dict[str, Any]) -> Any:
        """Place a sliced order. Raises if unsupported."""
        ...

    def set_kill_switch(self, payload: dict[str, Any]) -> Any:
        """Toggle the broker-side kill switch. Raises if unsupported."""
        ...


__all__ = ["OrderCapabilityPort"]
