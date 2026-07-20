"""Architecture ratchet — composition root exposes ServiceRegistry."""

from __future__ import annotations

from runtime.service_registry import ServiceRegistry


def test_service_registry_register_and_require() -> None:
    reg = ServiceRegistry()
    reg.register("lifecycle", object())
    assert reg.require("lifecycle") is not None
    assert reg.names() == frozenset({"lifecycle"})


def test_runtime_build_attaches_service_registry(monkeypatch) -> None:
    from runtime.factory import Runtime, build_from_broker_service, BuildOptions

    class _Lifecycle:
        def register(self, _svc) -> None:
            pass

    class _TC:
        event_bus = object()

    class _BrokerService:
        active_broker_name = "dhan"
        active_broker = None
        trading_context = _TC()
        lifecycle = _Lifecycle()
        http_observability = None
        live_actionable = False
        _event_bus = object()

        @property
        def gateways(self) -> dict:
            return {}

    monkeypatch.setattr(
        "runtime.production_config.validate_production_config",
        lambda **_: None,
    )
    monkeypatch.setattr(
        "runtime.parity_gate.assert_runtime_parity_or_raise",
        lambda: None,
    )
    monkeypatch.setattr(
        "runtime.composition.wire_domain_port_sinks",
        lambda: None,
    )
    monkeypatch.setattr(
        "runtime.live_datalake_wiring.wire_live_bar_sink",
        lambda *_a, **_k: None,
    )

    runtime = build_from_broker_service(
        _BrokerService(),
        options=BuildOptions(skip_parity_gate=True, wire_orchestrator=False),
    )
    assert isinstance(runtime, Runtime)
    assert runtime.service_registry is not None
    assert "lifecycle" in runtime.service_registry.names()
    assert "trading_context" in runtime.service_registry.names()
