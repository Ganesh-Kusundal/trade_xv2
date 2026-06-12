"""M4 — F13 regression: silent ``instrument=EQUITY`` fallback is gone.

Pre-fix, ``DhanBroker.get_historical_data`` resolved the symbol via the
legacy ``DhanInstrumentResolver`` and then wrapped the
``get_definition`` call in ``except Exception: pass``.  When the
catalog was empty (e.g. the F11 bug, or any race where
``load_instrument_catalog`` hadn't completed), a NIFTY index request
silently fell through to ``instrument=EQUITY`` and Dhan rejected the
request with a 4xx — operators had no clue the cause was a missing
catalog.

Post-fix, the new code resolves via :class:`InstrumentService`, derives
the ``instrument`` payload field from the resolved definition's actual
``instrument_type`` (INDEX / FUTURES / OPTIONS / COMMODITY / CURRENCY /
EQUITY), and raises :class:`InstrumentNotFoundError` if no definition
can be found.  There is no silent fallback.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from brokers.common.core.enums import ExchangeSegment
from brokers.dhan.broker import DhanBroker
from brokers.dhan.instrument_service import (
    InstrumentNotFoundError,
    InstrumentService,
)
from brokers.dhan.mapper.instruments import DhanInstrumentDefinition

pytestmark = pytest.mark.unit


def _make_definition(
    symbol: str,
    segment: ExchangeSegment,
    security_id: str,
    *,
    instrument_type: str = "INDEX",
) -> DhanInstrumentDefinition:
    """Build a minimal DhanInstrumentDefinition for tests."""
    return DhanInstrumentDefinition(
        symbol=symbol,
        canonical_symbol=symbol,
        exchange_segment=segment,
        security_id=security_id,
        instrument_type=instrument_type,
    )


class TestGetHistoricalDataInstrumentRouting:
    """F13 — ``instrument`` field is derived from the actual instrument type."""

    def _build_broker(self, tmp_path: Path) -> DhanBroker:
        return DhanBroker(
            client_id="TEST",
            access_token="T",
            instrument_service=InstrumentService(cache_dir=tmp_path / "instr"),
        )

    def test_index_request_threads_instrument_index(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        """NIFTY on IDX_I must request ``instrument=INDEX``, not ``EQUITY``."""
        broker = self._build_broker(tmp_path)
        broker.instrument_service.load_snapshot(real_csv_path)
        # Stub the market_data client to capture the kwargs passed in.
        captured: dict = {}

        def fake_history(
            security_id, segment, from_date, to_date, *, interval=None, instrument=None
        ):
            captured["security_id"] = security_id
            captured["segment"] = segment
            captured["instrument"] = instrument
            captured["interval"] = interval
            return []

        broker.market_data.get_historical_intraday = fake_history  # type: ignore[assignment]
        broker.get_historical_data("NIFTY", "IDX_I", date(2026, 1, 1), date(2026, 1, 5))
        assert captured["instrument"] == "INDEX", (
            f"Expected INDEX, got {captured['instrument']!r}. "
            "F13 regression — silent EQUITY fallback."
        )
        # NIFTY's actual SID in the committed fixture is 1 (the fixture
        # is a stratified sample; the audit's full-CSV pin was 13).
        # The contract we care about is the ``instrument`` field.
        assert captured["security_id"]

    def test_equity_request_threads_instrument_equity(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        broker = self._build_broker(tmp_path)
        broker.instrument_service.load_snapshot(real_csv_path)
        captured: dict = {}

        def fake_history(security_id, segment, from_date, to_date, **kwargs):
            captured.update(kwargs)
            captured["security_id"] = security_id
            captured["segment"] = segment
            return []

        broker.market_data.get_historical_intraday = fake_history  # type: ignore[assignment]
        broker.get_historical_data("RELIANCE", "NSE", date(2026, 1, 1), date(2026, 1, 5))
        assert captured["instrument"] == "EQUITY"
        assert captured["security_id"] == "2885"

    def test_unknown_symbol_raises_instrument_not_found(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        """When the catalog can't resolve the symbol, the broker must raise —
        not silently fall back to EQUITY.
        """
        broker = self._build_broker(tmp_path)
        broker.instrument_service.load_snapshot(real_csv_path)
        with pytest.raises(InstrumentNotFoundError):
            broker.get_historical_data(
                "TOTALLY_FAKE_SYMBOL_XYZ",
                "NSE",
                date(2026, 1, 1),
                date(2026, 1, 5),
            )
