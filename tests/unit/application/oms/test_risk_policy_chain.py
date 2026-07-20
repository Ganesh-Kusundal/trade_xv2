"""Risk policy chain ordering (CODE-001)."""

from __future__ import annotations

from application.oms._internal.risk_policies import RiskPolicyContext, run_policy_chain
from application.oms._internal.risk_types import RiskResult


class _FakeOrder:
    symbol = "TEST"
    exchange = "NSE"
    price = 0


def test_policy_chain_stops_at_first_denial() -> None:
    calls: list[str] = []

    def allow(_order, _ctx):
        calls.append("allow")
        return None

    def deny(_order, _ctx):
        calls.append("deny")
        return RiskResult(False, "no")

    def never(_order, _ctx):
        calls.append("never")
        return None

    result = run_policy_chain(_FakeOrder(), RiskPolicyContext(object()), [allow, deny, never])
    assert result is not None and not result.allowed
    assert calls == ["allow", "deny"]
