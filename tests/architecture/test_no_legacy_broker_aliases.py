"""Guardrail: DhanBrokerGateway / UpstoxBrokerGateway legacy aliases must not return.

Phase 3 of the broker infrastructure standardization removed these aliases.
This test prevents them from being re-introduced.
"""

import importlib


def test_no_dhan_broker_gateway_alias() -> None:
    """DhanBrokerGateway alias was removed — use DhanWireAdapter."""
    mod = importlib.import_module("brokers.dhan.wire")
    assert not hasattr(mod, "DhanBrokerGateway"), (
        "DhanBrokerGateway legacy alias must not exist. Use DhanWireAdapter."
    )
    assert hasattr(mod, "DhanWireAdapter"), (
        "DhanWireAdapter must exist (canonical name)."
    )


def test_no_upstox_broker_gateway_alias() -> None:
    """UpstoxBrokerGateway alias was removed — use UpstoxWireAdapter."""
    mod = importlib.import_module("brokers.upstox.wire")
    assert not hasattr(mod, "UpstoxBrokerGateway"), (
        "UpstoxBrokerGateway legacy alias must not exist. Use UpstoxWireAdapter."
    )
    assert hasattr(mod, "UpstoxWireAdapter"), (
        "UpstoxWireAdapter must exist (canonical name)."
    )


def test_all_wire_exports_are_canonical() -> None:
    """Wire adapter __all__ must contain only canonical names."""
    for mod_name, canonical in [
        ("brokers.dhan.wire", "DhanWireAdapter"),
        ("brokers.upstox.wire", "UpstoxWireAdapter"),
    ]:
        mod = importlib.import_module(mod_name)
        assert canonical in mod.__all__, (
            f"{mod_name}.__all__ must include {canonical!r}"
        )
        # No legacy aliases in __all__
        legacy_names = {"DhanBrokerGateway", "UpstoxBrokerGateway"}
        for name in mod.__all__:
            assert name not in legacy_names, (
                f"Legacy alias {name!r} must not appear in {mod_name}.__all__"
            )
