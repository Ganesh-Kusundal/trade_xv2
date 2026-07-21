"""Market-data CLI cmds must not force OMS event-log replay."""

from __future__ import annotations

import pytest

from interface.ui.main import MARKET_ONLY_CMDS


@pytest.mark.unit
def test_quote_skips_oms_bootstrap() -> None:
    assert "quote" in MARKET_ONLY_CMDS
    assert "option-chain" in MARKET_ONLY_CMDS
    assert "history" in MARKET_ONLY_CMDS
    # Order/OMS commands stay on the full bootstrap path.
    assert "oms" not in MARKET_ONLY_CMDS
