"""SM-10: BrokerId enum integration tests.

Verifies that broker_infrastructure.gateway_for and capabilities_for
accept the typed BrokerId enum (not just raw strings).
"""

from __future__ import annotations

import inspect

from domain.ports.broker_id import BrokerId
from runtime.broker_infrastructure import BrokerInfrastructure


def test_gateway_for_accepts_broker_id_enum():
    """gateway_for signature must accept BrokerId (a str subclass)."""
    sig = inspect.signature(BrokerInfrastructure.gateway_for)
    param = sig.parameters.get("broker_id")
    assert param is not None, "broker_id parameter missing from gateway_for"

    annotation = param.annotation
    # Accept str, BrokerId, or union containing BrokerId
    assert annotation is inspect.Parameter.empty or any(
        token in str(annotation) for token in ("BrokerId", "str | BrokerId", "Union[str, BrokerId]")
    ), f"Unexpected annotation: {annotation}"


def test_capabilities_for_accepts_broker_id_enum():
    """capabilities_for signature must accept BrokerId (a str subclass)."""
    sig = inspect.signature(BrokerInfrastructure.capabilities_for)
    param = sig.parameters.get("broker_id")
    assert param is not None, "broker_id parameter missing from capabilities_for"

    annotation = param.annotation
    assert annotation is inspect.Parameter.empty or any(
        token in str(annotation) for token in ("BrokerId", "str | BrokerId", "Union[str, BrokerId]")
    ), f"Unexpected annotation: {annotation}"


def test_broker_id_enum_values():
    """BrokerId must contain the canonical broker identifiers."""
    assert BrokerId.DHAN == "dhan"
    assert BrokerId.UPSTOX == "upstox"
    assert BrokerId.PAPER == "paper"


def test_broker_id_is_str_subclass():
    """BrokerId values should be usable anywhere a str is expected."""
    assert isinstance(BrokerId.DHAN, str)
    # String operations must work
    assert BrokerId.DHAN.upper() == "DHAN"
    assert BrokerId.DHAN + "_broker" == "dhan_broker"
