"""Live smoke — skipped unless DHAN_* / UPSTOX_* credentials are present."""

from __future__ import annotations

import os

import pytest

from plugins.brokers.dhan import DhanGateway
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.upstox import UpstoxGateway
from plugins.brokers.upstox.config import UpstoxConfig


def _has_dhan() -> bool:
    return bool(os.environ.get("DHAN_ACCESS_TOKEN") or (os.environ.get("DHAN_CLIENT_ID") and os.environ.get("DHAN_TOTP_SECRET")))


def _has_upstox() -> bool:
    return bool(
        os.environ.get("UPSTOX_ACCESS_TOKEN")
        or (os.environ.get("UPSTOX_MOBILE") and os.environ.get("UPSTOX_TOTP_SECRET"))
    )


@pytest.mark.live
@pytest.mark.skipif(not _has_dhan(), reason="DHAN credentials not set")
def test_dhan_live_authenticate() -> None:
    gw = DhanGateway(config=DhanConfig.from_env())
    gw.connect()
    assert gw.authenticate() is True
    funds = gw.get_funds()
    assert funds.balance.currency == "INR"
    gw.close()


@pytest.mark.live
@pytest.mark.skipif(not _has_upstox(), reason="UPSTOX credentials not set")
def test_upstox_live_authenticate() -> None:
    gw = UpstoxGateway(config=UpstoxConfig.from_env())
    gw.connect()
    assert gw.authenticate() is True
    funds = gw.get_funds()
    assert funds.balance.currency == "INR"
    gw.close()
