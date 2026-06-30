"""Tests for BrokerRouter — deterministic, auditable broker selection.

Covers:
- Fixed mode routing
- Priority-list mode with fallback
- Capability filtering (required_features, policy features)
- Health filtering (unhealthy brokers rejected)
- Quota-aware mode (best headroom wins)
- Latency-aware mode (lowest p50 wins)
- No eligible broker → RoutingError
- Parallellism for historical federation
- Audit decision logging
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from brokers.common.capabilities import (
    BrokerCapabilities,
    CapabilityDescriptor,
)
from brokers.common.errors import RoutingError
from brokers.common.models import (
    BrokerHealthSnapshot,
    OperationKind,
    RoutingRequest,
)
from brokers.common.policy import (
    RoutingPolicy,
    SourceSelectionPolicy,
)
from brokers.common.registry import BrokerRegistry
from brokers.common.router import BrokerRouter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(
    brokers: dict[str, BrokerCapabilities],
    health: dict[str, BrokerHealthSnapshot] | None = None,
) -> BrokerRegistry:
    """Build a BrokerRegistry with pre-populated capabilities and health."""
    registry = BrokerRegistry()
    for broker_id, caps in brokers.items():
        gw = MagicMock()
        gw.broker_id = broker_id
        gw.list_capabilities.return_value = CapabilityDescriptor(
            broker_id=broker_id,
            capabilities=caps,
            extensions=frozenset(),
            observed_at=datetime.now(tz=timezone.utc),
        )
        # Directly inject into registry internals for testing
        registry._gateways[broker_id] = gw
        registry._capabilities[broker_id] = CapabilityDescriptor(
            broker_id=broker_id,
            capabilities=caps,
            extensions=frozenset(),
            observed_at=datetime.now(tz=timezone.utc),
        )
        registry._health[broker_id] = (
            health.get(broker_id, BrokerHealthSnapshot(broker_id=broker_id, alive=True))
            if health is not None
            else BrokerHealthSnapshot(broker_id=broker_id, alive=True)
        )
    return registry


def _make_policy(
    mode: str = "fixed",
    candidates: tuple[str, ...] = ("dhan",),
    allow_fallback: bool = True,
    required_features: frozenset[str] = frozenset(),
    max_parallel_sources: int | None = None,
) -> SourceSelectionPolicy:
    """Build a SourceSelectionPolicy with the given routing config."""
    policy = RoutingPolicy(
        mode=mode,
        candidates=candidates,
        allow_fallback=allow_fallback,
        required_features=required_features,
        max_parallel_sources=max_parallel_sources,
    )
    return SourceSelectionPolicy(
        historical=policy,
        live_market_data=policy,
        execution=policy,
        enrichment=policy,
        instrument_metadata=policy,
    )


def _request(
    operation: OperationKind = OperationKind.GET_QUOTE,
    features: frozenset[str] = frozenset(),
    trace_id: str = "test-trace",
) -> RoutingRequest:
    return RoutingRequest(
        operation=operation,
        trace_id=trace_id,
        required_features=features,
    )


# ---------------------------------------------------------------------------
# Capability filtering
# ---------------------------------------------------------------------------


class TestCapabilityFiltering:
    def test_filters_broker_missing_required_feature(self) -> None:
        """Broker without requested feature should be rejected."""
        dhan_caps = BrokerCapabilities(
            broker_id="dhan",
            supports_place_order=True,
            supports_historical_data=True,
        )
        upstox_caps = BrokerCapabilities(
            broker_id="upstox",
            supports_place_order=True,
            supports_historical_data=False,
        )
        registry = _make_registry({"dhan": dhan_caps, "upstox": upstox_caps})
        policy = _make_policy(mode="priority_list", candidates=("upstox", "dhan"))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request(features=frozenset({"historical_data"})))
        assert decision.primary_broker == "dhan"

    def test_policy_required_features_checked(self) -> None:
        """Per-policy required_features should also filter candidates."""
        dhan_caps = BrokerCapabilities(broker_id="dhan", supports_place_order=True)
        registry = _make_registry({"dhan": dhan_caps})
        policy = _make_policy(
            mode="capability_match",
            candidates=("dhan",),
            required_features=frozenset({"news"}),  # Dhan doesn't have news
        )
        router = BrokerRouter(registry, policy)

        with pytest.raises(RoutingError, match="no healthy capable broker"):
            router.route(_request(operation=OperationKind.FETCH_NEWS))


# ---------------------------------------------------------------------------
# Health filtering
# ---------------------------------------------------------------------------


class TestHealthFiltering:
    def test_unhealthy_broker_rejected(self) -> None:
        """Unhealthy broker should be skipped in favor of healthy one."""
        dhan_health = BrokerHealthSnapshot(
            broker_id="dhan", alive=False, reason="auth expired"
        )
        upstox_health = BrokerHealthSnapshot(broker_id="upstox", alive=True)
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
            health={"dhan": dhan_health, "upstox": upstox_health},
        )
        policy = _make_policy(mode="priority_list", candidates=("dhan", "upstox"))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "upstox"
        assert "dhan" in decision.rejected

    def test_all_unhealthy_raises_routing_error(self) -> None:
        """When all brokers are unhealthy, RoutingError is raised."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan")},
            health={"dhan": BrokerHealthSnapshot(broker_id="dhan", alive=False)},
        )
        policy = _make_policy()
        router = BrokerRouter(registry, policy)

        with pytest.raises(RoutingError, match="no healthy capable broker"):
            router.route(_request())


# ---------------------------------------------------------------------------
# Fixed mode
# ---------------------------------------------------------------------------


class TestFixedMode:
    def test_always_selects_first_candidate(self) -> None:
        """Fixed mode always returns candidates[0] as primary."""
        registry = _make_registry({"dhan": BrokerCapabilities(broker_id="dhan")})
        policy = _make_policy(mode="fixed", candidates=("dhan",), allow_fallback=False)
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "dhan"
        assert not decision.has_fallback()


# ---------------------------------------------------------------------------
# Priority list mode
# ---------------------------------------------------------------------------


class TestPriorityListMode:
    def test_selects_first_healthy(self) -> None:
        """Priority list selects first healthy candidate."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
        )
        policy = _make_policy(mode="priority_list", candidates=("upstox", "dhan"))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "upstox"

    def test_fallback_to_second_broker(self) -> None:
        """When primary is unhealthy, falls back to second broker."""
        upstox_health = BrokerHealthSnapshot(broker_id="upstox", alive=False, reason="down")
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
            health={"upstox": upstox_health},
        )
        policy = _make_policy(mode="priority_list", candidates=("upstox", "dhan"), allow_fallback=True)
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "dhan"
        assert "upstox" in decision.rejected

    def test_no_fallback_when_disabled(self) -> None:
        """When allow_fallback=False, only primary is used."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
        )
        policy = _make_policy(mode="priority_list", candidates=("dhan", "upstox"), allow_fallback=False)
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "dhan"
        assert decision.fallback_brokers == ()


# ---------------------------------------------------------------------------
# Quota-aware mode
# ---------------------------------------------------------------------------


class TestQuotaAwareMode:
    def test_selects_broker_with_most_headroom(self) -> None:
        """Quota-aware mode picks the broker with highest headroom."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
        )
        policy = _make_policy(mode="quota_aware", candidates=("dhan", "upstox"))

        def quota_fn(broker_id: str, endpoint_class: str) -> float:
            return {"dhan": 0.3, "upstox": 0.9}[broker_id]

        router = BrokerRouter(registry, policy, quota_headroom_fn=quota_fn)
        decision = router.route(_request())
        assert decision.primary_broker == "upstox"  # 90% headroom wins


# ---------------------------------------------------------------------------
# Latency-aware mode
# ---------------------------------------------------------------------------


class TestLatencyAwareMode:
    def test_selects_lowest_latency(self) -> None:
        """Latency-aware mode picks broker with lowest p50 latency."""
        dhan_health = BrokerHealthSnapshot(broker_id="dhan", alive=True, latency_p50_ms=45.0)
        upstox_health = BrokerHealthSnapshot(broker_id="upstox", alive=True, latency_p50_ms=120.0)
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
            health={"dhan": dhan_health, "upstox": upstox_health},
        )
        policy = _make_policy(mode="latency_aware", candidates=("upstox", "dhan"))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert decision.primary_broker == "dhan"  # 45ms < 120ms


# ---------------------------------------------------------------------------
# Parallel routing for historical federation
# ---------------------------------------------------------------------------


class TestParallelRouting:
    def test_parallel_historical_federation(self) -> None:
        """Historical mode with max_parallel_sources > 1 returns parallel brokers."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
        )
        policy = _make_policy(
            mode="capability_match",
            candidates=("upstox", "dhan"),
            max_parallel_sources=2,
        )
        router = BrokerRouter(registry, policy)

        decision = router.route(_request(operation=OperationKind.GET_HISTORICAL_BARS))
        assert len(decision.parallel_brokers) == 2

    def test_parallel_not_used_for_non_historical(self) -> None:
        """Parallel routing only applies to GET_HISTORICAL_BARS."""
        registry = _make_registry(
            {"dhan": BrokerCapabilities(broker_id="dhan"), "upstox": BrokerCapabilities(broker_id="upstox")},
        )
        policy = _make_policy(
            mode="capability_match",
            candidates=("upstox", "dhan"),
            max_parallel_sources=2,
        )
        router = BrokerRouter(registry, policy)

        decision = router.route(_request(operation=OperationKind.GET_QUOTE))
        assert decision.parallel_brokers == ()


# ---------------------------------------------------------------------------
# Decision audit
# ---------------------------------------------------------------------------


class TestDecisionAudit:
    def test_decision_has_reason_codes(self) -> None:
        """Decision should include reason codes for audit trail."""
        registry = _make_registry({"dhan": BrokerCapabilities(broker_id="dhan")})
        policy = _make_policy(mode="fixed", candidates=("dhan",))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        assert any("mode:fixed" in code for code in decision.reason_codes)
        assert any("selected:dhan" in code for code in decision.reason_codes)

    def test_decision_has_trace_id(self) -> None:
        """Decision should echo the trace_id from the request."""
        registry = _make_registry({"dhan": BrokerCapabilities(broker_id="dhan")})
        policy = _make_policy(mode="fixed", candidates=("dhan",))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request(trace_id="my-trace-123"))
        assert decision.trace_id == "my-trace-123"

    def test_to_audit_dict(self) -> None:
        """to_audit_dict should return a structured dict for logging."""
        registry = _make_registry({"dhan": BrokerCapabilities(broker_id="dhan")})
        policy = _make_policy(mode="fixed", candidates=("dhan",))
        router = BrokerRouter(registry, policy)

        decision = router.route(_request())
        audit = decision.to_audit_dict()
        assert audit["event"] == "routing.decision"
        assert audit["primary_broker"] == "dhan"
        assert "decided_at" in audit
