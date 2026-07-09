"""Broker-common lifecycle re-exports.

``LifecycleManager`` is implemented in ``infrastructure.lifecycle.lifecycle``.
This module re-exports it so ``brokers.common`` (and anything importing
``brokers.common.lifecycle``) keeps a stable import path without taking a
direct ``brokers.common -> infrastructure.lifecycle`` dependency at every
call site.  ``Broker common isolation`` permits ``brokers.common ->
infrastructure`` (only broker *implementations* and ``analytics`` are
forbidden), so this re-export is contract-clean.
"""

from infrastructure.lifecycle.lifecycle import LifecycleManager

__all__ = ["LifecycleManager"]
