"""Tests for domain policies: SourceSelectionPolicy and RoutingPolicy."""

from __future__ import annotations

import pytest

from domain.enums import BrokerId, ExchangeId
from domain.policies import RoutingPolicy
from domain.policies.routing import RoutingRule
from domain.policies.source_selection import DataSourceKind, SourceSelectionPolicy
from domain.value_objects import InstrumentId, TimeFrame


# ---------------------------------------------------------------------------
# Helper: fake implementations for protocol testing
# ---------------------------------------------------------------------------

class _AlwaysLocalPolicy:
    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind:
        return DataSourceKind.DATALAKE


class _AlwaysBrokerPolicy:
    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind:
        return DataSourceKind.BROKER_HISTORICAL


class _AlwaysFederatedPolicy:
    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind:
        return DataSourceKind.FEDERATED


class _FakeSourceSelectionPolicy:
    """Concrete policy that returns DATALAKE for NSE, BROKER_HISTORICAL for others."""

    def select(self, instrument_id: InstrumentId, timeframe: TimeFrame) -> DataSourceKind:
        if instrument_id.value.startswith("NSE:"):
            return DataSourceKind.DATALAKE
        return DataSourceKind.BROKER_HISTORICAL


class _FakeRoutingPolicy:
    """Concrete policy that routes NSE to DHAN, others to UPSTOX."""

    def route(self, instrument_id: InstrumentId) -> BrokerId:
        if instrument_id.value.startswith("NSE:"):
            return BrokerId.DHAN
        return BrokerId.UPSTOX


# ---------------------------------------------------------------------------
# SourceSelectionPolicy — Protocol conformance
# ---------------------------------------------------------------------------

class TestSourceSelectionPolicyProtocol:
    def test_always_local_is_protocol(self) -> None:
        assert isinstance(_AlwaysLocalPolicy(), SourceSelectionPolicy)

    def test_always_broker_is_protocol(self) -> None:
        assert isinstance(_AlwaysBrokerPolicy(), SourceSelectionPolicy)

    def test_always_federated_is_protocol(self) -> None:
        assert isinstance(_AlwaysFederatedPolicy(), SourceSelectionPolicy)


# ---------------------------------------------------------------------------
# SourceSelectionPolicy — Default resolution order
# ---------------------------------------------------------------------------

class TestSourceSelectionResolutionOrder:
    def test_local_when_available(self) -> None:
        policy = _FakeSourceSelectionPolicy()
        iid = InstrumentId(value="NSE:RELIANCE")
        tf = TimeFrame(value="1d")
        assert policy.select(iid, tf) is DataSourceKind.DATALAKE

    def test_broker_when_not_local(self) -> None:
        policy = _FakeSourceSelectionPolicy()
        iid = InstrumentId(value="BSE:TCS")
        tf = TimeFrame(value="1d")
        assert policy.select(iid, tf) is DataSourceKind.BROKER_HISTORICAL

    def test_federated_fallback(self) -> None:
        policy = _AlwaysFederatedPolicy()
        iid = InstrumentId(value="MCX:GOLD")
        tf = TimeFrame(value="1m")
        assert policy.select(iid, tf) is DataSourceKind.FEDERATED


# ---------------------------------------------------------------------------
# DataSourceKind — Enum values
# ---------------------------------------------------------------------------

class TestDataSourceKind:
    def test_has_three_variants(self) -> None:
        assert len(DataSourceKind) == 3

    def test_datalake_value(self) -> None:
        assert DataSourceKind.DATALAKE.value == "DATALAKE"

    def test_broker_historical_value(self) -> None:
        assert DataSourceKind.BROKER_HISTORICAL.value == "BROKER_HISTORICAL"

    def test_federated_value(self) -> None:
        assert DataSourceKind.FEDERATED.value == "FEDERATED"


# ---------------------------------------------------------------------------
# RoutingPolicy — Protocol conformance
# ---------------------------------------------------------------------------

class TestRoutingPolicyProtocol:
    def test_fake_is_protocol(self) -> None:
        assert isinstance(_FakeRoutingPolicy(), RoutingPolicy)

    def test_protocol_with_matching_method(self) -> None:
        class _PaperRouter:
            def route(self, instrument_id: InstrumentId) -> BrokerId:
                return BrokerId.PAPER
        assert isinstance(_PaperRouter(), RoutingPolicy)


# ---------------------------------------------------------------------------
# RoutingPolicy — Selects broker based on instrument
# ---------------------------------------------------------------------------

class TestRoutingSelection:
    def test_nse_routes_to_dhan(self) -> None:
        policy = _FakeRoutingPolicy()
        iid = InstrumentId(value="NSE:RELIANCE")
        assert policy.route(iid) is BrokerId.DHAN

    def test_bse_routes_to_upstox(self) -> None:
        policy = _FakeRoutingPolicy()
        iid = InstrumentId(value="BSE:TCS")
        assert policy.route(iid) is BrokerId.UPSTOX


# ---------------------------------------------------------------------------
# RoutingRule — Value object
# ---------------------------------------------------------------------------

class TestRoutingRule:
    def test_fields(self) -> None:
        rule = RoutingRule(
            exchange=ExchangeId.NSE,
            broker=BrokerId.DHAN,
        )
        assert rule.exchange is ExchangeId.NSE
        assert rule.broker is BrokerId.DHAN

    def test_frozen(self) -> None:
        rule = RoutingRule(exchange=ExchangeId.MCX, broker=BrokerId.PAPER)
        with pytest.raises(AttributeError):
            rule.broker = BrokerId.DHAN  # type: ignore[misc]
