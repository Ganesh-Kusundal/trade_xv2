"""Regression: capability validator flag names match BrokerCapabilities fields."""

from __future__ import annotations

from dataclasses import fields

import pytest

from brokers.common.capabilities_validator import _CAPABILITY_METHOD_MAP
from domain.capabilities.broker_capabilities import BrokerCapabilities


@pytest.mark.architecture
def test_capability_method_map_keys_exist_on_broker_capabilities() -> None:
    cap_fields = {f.name for f in fields(BrokerCapabilities)}
    unknown = [key for key in _CAPABILITY_METHOD_MAP if key not in cap_fields]
    assert not unknown, f"Unknown capability flags in validator map: {unknown}"
