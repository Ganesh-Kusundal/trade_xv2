from brokers.upstox.status_mapper import UPSTOX_STATUS_MAP
from domain import OrderStatus


def test_cancel_pending_stays_non_terminal():
    assert UPSTOX_STATUS_MAP["CANCEL_PENDING"] == OrderStatus.OPEN
