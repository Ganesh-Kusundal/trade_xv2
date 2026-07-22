"""Domain enumeration contract tests."""

from enum import StrEnum

from domain.enums import (
    AssetClass,
    BrokerId,
    Currency,
    ComponentState,
    DriftSeverity,
    Environment,
    ExchangeId,
    ExecutionTargetKind,
    InstrumentType,
    OptionType,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskLevel,
    SignalDirection,
    TimeInForce,
)


# ── Membership tests ──────────────────────────────────────────────

def test_order_side_values() -> None:
    assert OrderSide.BUY.value == "BUY"
    assert OrderSide.SELL.value == "SELL"


def test_order_type_values() -> None:
    assert {t.name for t in OrderType} == {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}


def test_order_status_values() -> None:
    assert {s.name for s in OrderStatus} == {
        "PENDING",
        "SUBMITTED",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "REJECTED",
        "UNKNOWN",
    }


def test_time_in_force_values() -> None:
    assert {t.name for t in TimeInForce} == {"DAY", "IOC", "GTC"}


def test_environment_values() -> None:
    assert {e.name for e in Environment} == {"REPLAY", "BACKTEST", "PAPER", "LIVE"}


def test_execution_target_kind_values() -> None:
    assert {k.name for k in ExecutionTargetKind} == {"REPLAY", "SIMULATED", "PAPER", "BROKER"}


def test_broker_id_values() -> None:
    assert {b.name for b in BrokerId} == {"DHAN", "UPSTOX", "PAPER"}


def test_exchange_id_values() -> None:
    assert {e.name for e in ExchangeId} == {"NSE", "BSE", "MCX"}


def test_asset_class_and_instrument_type() -> None:
    assert {a.name for a in AssetClass} == {"EQUITY", "DERIVATIVE", "COMMODITY", "CURRENCY"}
    assert {t.name for t in InstrumentType} == {"EQUITY", "FUTURE", "OPTION", "INDEX"}


def test_option_signal_risk_drift_component() -> None:
    assert {o.name for o in OptionType} == {"CALL", "PUT"}
    assert {d.name for d in SignalDirection} == {"BUY", "SELL", "NEUTRAL"}
    assert {r.name for r in RiskLevel} == {"INFO", "WARNING", "CRITICAL"}
    assert {d.name for d in DriftSeverity} == {"LOW", "MEDIUM", "HIGH"}
    assert {s.name for s in ComponentState} == {
        "UNINITIALIZED",
        "INITIALIZED",
        "RUNNING",
        "STOPPED",
        "ERROR",
    }


def test_currency_value() -> None:
    assert Currency.INR.value == "INR"
    assert {c.name for c in Currency} == {"INR"}


# ── StrEnum serialization tests ────────────────────────────────────

def test_all_enums_are_strenum() -> None:
    """Every domain enum must be a StrEnum for JSON serialization."""
    enums = [
        OrderSide, OrderType, OrderStatus, TimeInForce,
        Environment, ExecutionTargetKind, BrokerId, ExchangeId,
        AssetClass, InstrumentType, OptionType, SignalDirection,
        RiskLevel, DriftSeverity, Currency, ComponentState,
    ]
    for enum_cls in enums:
        assert issubclass(enum_cls, StrEnum), f"{enum_cls.__name__} is not a StrEnum"


def test_strenum_values_are_strings() -> None:
    """StrEnum members serialize directly as their value."""
    assert str(OrderSide.BUY) == "BUY"
    assert str(OrderSide.SELL) == "SELL"
    assert str(OrderType.MARKET) == "MARKET"
    assert str(OrderStatus.PENDING) == "PENDING"
    assert str(TimeInForce.DAY) == "DAY"
    assert str(Environment.LIVE) == "LIVE"
    assert str(ExecutionTargetKind.BROKER) == "BROKER"
    assert str(BrokerId.DHAN) == "DHAN"
    assert str(ExchangeId.NSE) == "NSE"
    assert str(AssetClass.EQUITY) == "EQUITY"
    assert str(InstrumentType.FUTURE) == "FUTURE"
    assert str(OptionType.CALL) == "CALL"
    assert str(SignalDirection.NEUTRAL) == "NEUTRAL"
    assert str(RiskLevel.CRITICAL) == "CRITICAL"
    assert str(DriftSeverity.HIGH) == "HIGH"
    assert str(Currency.INR) == "INR"
    assert str(ComponentState.RUNNING) == "RUNNING"


def test_strenum_json_serializable() -> None:
    """StrEnum members can be used directly in JSON."""
    import json
    data = {"side": OrderSide.BUY, "status": OrderStatus.FILLED}
    result = json.dumps(data)
    assert '"BUY"' in result
    assert '"FILLED"' in result
