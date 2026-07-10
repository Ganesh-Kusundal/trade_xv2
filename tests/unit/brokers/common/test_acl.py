"""ACL normalize_order_status — OrderStatus always enum at the boundary."""

from __future__ import annotations

from brokers.common.acl import DefaultBrokerTranslator, normalize_order_status
from domain import OrderStatus


def test_normalize_common_broker_statuses():
    assert normalize_order_status("COMPLETE") == OrderStatus.FILLED
    assert normalize_order_status("EXECUTED") == OrderStatus.FILLED
    assert normalize_order_status(OrderStatus.OPEN) == OrderStatus.OPEN
    assert normalize_order_status(None) == OrderStatus.UNKNOWN


def test_default_translator():
    t = DefaultBrokerTranslator()
    assert t.status("TRANSIT") == OrderStatus.OPEN
