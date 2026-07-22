"""Unit tests for domain enums and exception hierarchy standardization."""

from domain.enums import PositionSide, Side
from domain.exceptions import BrokerError, ConfigError, OrderError, TradeXV2Error, ValidationError


def test_position_side_enum():
    assert PositionSide.LONG.value == "LONG"
    assert PositionSide.SHORT.value == "SHORT"
    assert PositionSide.FLAT.value == "FLAT"


def test_exception_hierarchy():
    err = OrderError("Invalid order state transition")
    assert isinstance(err, TradeXV2Error)

    broker_err = BrokerError("Gateway timeout")
    assert isinstance(broker_err, TradeXV2Error)

    val_err = ValidationError("Invalid quantity")
    assert isinstance(val_err, TradeXV2Error)

    cfg_err = ConfigError("Missing API key")
    assert isinstance(cfg_err, TradeXV2Error)
