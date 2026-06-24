"""Tests for broker_registry.py — create_gateway() event_bus/lifecycle forwarding.

Verifies that create_gateway() correctly forwards event_bus and lifecycle
parameters to both Dhan and Upstox factories, and that the Path conversion
for env_path works correctly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _skip_credential_gate(monkeypatch):
    """Registry unit tests mock factories; skip live credential validation."""
    from brokers.common.connection.authenticated_readiness import AuthProbeResult

    monkeypatch.setattr(
        "cli.services.broker_registry.CredentialValidator.validate_broker",
        lambda broker, env_path=None: (True, []),
    )
    monkeypatch.setattr(
        "cli.services.broker_registry.authenticated_readiness_probe",
        lambda gw, broker: AuthProbeResult(ok=True, probe_name="mock"),
    )


class TestCreateGatewayBasic:
    """Verify create_gateway() creates gateways for known brokers."""

    def test_unknown_broker_returns_none(self):
        """Unknown broker name must return None and log an error."""
        from cli.services.broker_registry import create_gateway

        result = create_gateway("nonexistent_broker")
        assert result is None

    def test_paper_gateway_returns_paper(self):
        """'paper' broker must return a PaperGateway instance."""
        from cli.services.broker_registry import create_gateway

        result = create_gateway("paper")
        assert result is not None
        from brokers.paper.paper_gateway import PaperGateway

        assert isinstance(result, PaperGateway)

    def test_broker_name_is_case_insensitive(self):
        """create_gateway('Paper') must work the same as 'paper'."""
        from cli.services.broker_registry import create_gateway

        result = create_gateway("Paper")
        assert result is not None
        from brokers.paper.paper_gateway import PaperGateway

        assert isinstance(result, PaperGateway)


class TestCreateGatewayEventBusForwarding:
    """Verify event_bus is forwarded to factory.create()."""

    def test_dhan_factory_receives_event_bus(self, monkeypatch, tmp_path):
        """create_gateway('dhan', event_bus=...) must pass event_bus to BrokerFactory."""
        from cli.services.broker_registry import create_gateway

        captured = {}
        mock_bus = MagicMock(name="event_bus")

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway(
            "dhan",
            env_path=tmp_path / ".env",
            load_instruments=False,
            event_bus=mock_bus,
        )

        assert "event_bus" in captured
        assert captured["event_bus"] is mock_bus

    def test_upstox_factory_receives_event_bus(self, monkeypatch, tmp_path):
        """create_gateway('upstox', event_bus=...) must pass event_bus to UpstoxBrokerFactory."""
        from cli.services.broker_registry import create_gateway

        captured = {}
        mock_bus = MagicMock(name="event_bus")

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.upstox.factory.UpstoxBrokerFactory", FakeFactory
        )

        create_gateway(
            "upstox",
            env_path=tmp_path / ".env",
            load_instruments=False,
            event_bus=mock_bus,
        )

        assert "event_bus" in captured
        assert captured["event_bus"] is mock_bus

    def test_event_bus_defaults_to_none(self, monkeypatch, tmp_path):
        """When no event_bus is passed, factory must receive None."""
        from cli.services.broker_registry import create_gateway

        captured = {}

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway("dhan", env_path=tmp_path / ".env", load_instruments=False)

        assert captured.get("event_bus") is None


class TestCreateGatewayLifecycleForwarding:
    """Verify lifecycle is forwarded to factory.create()."""

    def test_dhan_factory_receives_lifecycle(self, monkeypatch, tmp_path):
        """create_gateway('dhan', lifecycle=...) must pass lifecycle to BrokerFactory."""
        from cli.services.broker_registry import create_gateway

        captured = {}
        mock_lifecycle = MagicMock(name="lifecycle")

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway(
            "dhan",
            env_path=tmp_path / ".env",
            load_instruments=False,
            lifecycle=mock_lifecycle,
        )

        assert "lifecycle" in captured
        assert captured["lifecycle"] is mock_lifecycle

    def test_upstox_factory_receives_lifecycle(self, monkeypatch, tmp_path):
        """create_gateway('upstox', lifecycle=...) must pass lifecycle to UpstoxBrokerFactory."""
        from cli.services.broker_registry import create_gateway

        captured = {}
        mock_lifecycle = MagicMock(name="lifecycle")

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.upstox.factory.UpstoxBrokerFactory", FakeFactory
        )

        create_gateway(
            "upstox",
            env_path=tmp_path / ".env",
            load_instruments=False,
            lifecycle=mock_lifecycle,
        )

        assert "lifecycle" in captured
        assert captured["lifecycle"] is mock_lifecycle

    def test_lifecycle_defaults_to_none(self, monkeypatch, tmp_path):
        """When no lifecycle is passed, factory must receive None."""
        from cli.services.broker_registry import create_gateway

        captured = {}

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway("dhan", env_path=tmp_path / ".env", load_instruments=False)

        assert captured.get("lifecycle") is None


class TestCreateGatewayEnvPathConversion:
    """Verify env_path is correctly converted from str to Path."""

    def test_string_env_path_converted_to_path(self, monkeypatch):
        """A string env_path must be converted to a Path before passing to factory."""
        from cli.services.broker_registry import create_gateway

        captured = {}

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway("dhan", env_path="/some/path/.env", load_instruments=False)

        assert "env_path" in captured
        assert isinstance(captured["env_path"], Path)
        assert str(captured["env_path"]) == "/some/path/.env"

    def test_none_env_path_remains_none(self, monkeypatch):
        """A None env_path must remain None (not be converted to Path)."""
        from cli.services.broker_registry import create_gateway

        captured = {}

        class FakeGateway:
            _conn = MagicMock()

            def close(self):
                pass

        class FakeFactory:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return FakeGateway()

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FakeFactory
        )

        create_gateway("dhan", env_path=None, load_instruments=False)

        assert "env_path" in captured
        assert captured["env_path"] is None


class TestCreateGatewayErrorHandling:
    """Verify factory errors are caught and return None."""

    def test_dhan_factory_error_returns_none(self, monkeypatch, tmp_path):
        """If BrokerFactory.create() raises, create_gateway must return None."""
        from cli.services.broker_registry import create_gateway

        class FailingFactory:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("simulated failure")

        monkeypatch.setattr(
            "brokers.dhan.factory.BrokerFactory", FailingFactory
        )

        result = create_gateway("dhan", env_path=tmp_path / ".env")
        assert result is None

    def test_upstox_factory_error_returns_none(self, monkeypatch, tmp_path):
        """If UpstoxBrokerFactory.create() raises, create_gateway must return None."""
        from cli.services.broker_registry import create_gateway

        class FailingFactory:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("simulated failure")

        monkeypatch.setattr(
            "brokers.upstox.factory.UpstoxBrokerFactory", FailingFactory
        )

        result = create_gateway("upstox", env_path=tmp_path / ".env")
        assert result is None
