"""Architecture — ban legacy ``BrokerAdapter as MarketDataGateway`` alias in src/."""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC = _PROJECT_ROOT / "src"
_BANNED = "BrokerAdapter as MarketDataGateway"


@pytest.mark.architecture
def test_src_does_not_import_market_data_gateway_alias() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        text = path.read_text()
        if _BANNED in text:
            offenders.append(str(path.relative_to(_PROJECT_ROOT)))
    assert not offenders, (
        "Use WireBroker for wire holders, BrokerAdapter for InstrumentId ports, "
        f"MarketDataGatewayAdapter for composer wraps — not {_BANNED!r}: {offenders}"
    )
