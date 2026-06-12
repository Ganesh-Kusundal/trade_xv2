"""M3 — broker owns an InstrumentService.

Verifies that :class:`DhanBroker` exposes ``instrument_service``,
``refresh_instrument_snapshot``, and ``resolve_instrument`` as the new
canonical surface.  The existing ``instrument_resolver`` attribute is
retained for back-compat with the 11 call-site migration that follows
in subsequent commits.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from brokers.dhan.broker import DhanBroker
from brokers.dhan.instrument_service import (
    InstrumentService,
    SnapshotInfo,
)

pytestmark = pytest.mark.unit


def _build_broker(tmp_path: Path) -> DhanBroker:
    """Build a DhanBroker with an isolated instrument cache dir."""
    return DhanBroker(
        client_id="TEST_CLIENT",
        access_token="TEST_TOKEN",
        instrument_service=InstrumentService(cache_dir=tmp_path / "instr"),
    )


class TestBrokerInstrumentServiceWiring:
    """The broker must expose the M3 service surface."""

    def test_broker_has_instrument_service_attribute(self, tmp_path: Path) -> None:
        broker = _build_broker(tmp_path)
        assert isinstance(broker.instrument_service, InstrumentService)

    def test_broker_resolve_instrument_returns_sid(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        broker = _build_broker(tmp_path)
        broker.instrument_service.load_snapshot(real_csv_path)
        sid = broker.resolve_instrument("RELIANCE", "NSE")
        assert sid == "2885"

    def test_broker_refresh_instrument_snapshot_force(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        """refresh_instrument_snapshot should call the service and return SnapshotInfo."""
        broker = _build_broker(tmp_path)
        with patch.object(
            broker.instrument_service,
            "refresh_snapshot",
            return_value=SnapshotInfo(
                date="2026-06-11",
                checksum="deadbeef" * 8,
                record_count=17628,
                source_path=real_csv_path,
                wire_url="https://images.dhan.co/api-data/api-scrip-master.csv",
            ),
        ) as mock_refresh:
            info = broker.refresh_instrument_snapshot(force=True)
        assert isinstance(info, SnapshotInfo)
        mock_refresh.assert_called_once_with(force=True)

    def test_broker_load_instrument_catalog_mirrors_to_service(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        """load_instrument_catalog should also load the snapshot into the service."""
        broker = _build_broker(tmp_path)
        broker.load_instrument_catalog(real_csv_path)
        # The service now knows about RELIANCE.
        sid = broker.resolve_instrument("RELIANCE", "NSE")
        assert sid == "2885"

    def test_adapters_share_broker_instrument_service(
        self, tmp_path: Path, real_csv_path: Path
    ) -> None:
        broker = _build_broker(tmp_path)
        broker.instrument_service.load_snapshot(real_csv_path)
        assert broker.order_command._instrument_service is broker.instrument_service
        assert broker.order_validator._instrument_service is broker.instrument_service
        assert broker.futures._instrument_service is broker.instrument_service

    def test_broker_inherits_strict_resolution_setting(self, tmp_path: Path) -> None:
        """When no service is passed, the broker must use the settings.strict flag."""
        from brokers.dhan.auth.config import DhanConnectionSettings

        broker = DhanBroker(
            settings=DhanConnectionSettings(
                client_id="X",
                access_token="T",
                instrument_strict_resolution=False,
            )
        )
        assert broker.instrument_service._strict_resolution is False
