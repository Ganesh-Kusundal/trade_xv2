"""Broker margin adapter helpers — **not** the OMS.

The canonical order-management system lives in :mod:`application.oms`.

This package only hosts broker-side adapters used by risk checks
(e.g. :class:`BrokerMarginProvider`) and optional bootstrap re-exports
in :mod:`brokers.common.oms.defaults`. It must never grow order managers,
trading context, or other OMS core types.
"""

from brokers.common.oms.margin_provider import BrokerMarginProvider

__all__ = ["BrokerMarginProvider"]
