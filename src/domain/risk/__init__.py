"""Domain risk policies — pure, composable business rules for pre-trade risk.

These policy objects encapsulate risk logic that previously lived in
``application/oms/_internal/risk_manager.py``. Each policy is a testable,
stateless (or lightly stateful) value object: no infrastructure, no broker
references, no service singletons. Application workflows compose policies
and delegate to them — the policies never know about orders, gateways, or
REST payloads.

    risk = RiskGate(
        notional=OrderNotionalLimit(max=Decimal("500000")),
        concentration=ConcentrationLimit(max_pct=Decimal("0.20")),
        circuit_breaker=DailyLossCircuitBreaker(limit=Decimal("100000")),
    )
    result = risk.check_order(order_notional, portfolio_notional)
    if not result.approved: reject(reason=result.reason)
"""
