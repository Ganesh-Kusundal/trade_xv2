# ADR-006: Kill switch via injected RiskManagerPort

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
`TradingOrchestrator._is_kill_switch_active()` reached into
`self._order_manager.risk_manager` via `getattr` (`src/application/trading/
trading_orchestrator.py`, formerly line 518). This is fragile: a rename of the
internal `risk_manager` attribute would silently break the kill switch with no
compile-time signal, and an injected risk manager would be ignored. The roadmap
(ADR-002 / G7) called for a `RiskGate` port — but `domain.ports.risk_manager.
RiskManagerPort` already exists with `is_kill_switch_active()`. Adding a new
`RiskGate` would be speculative duplication (ponytail: reuse before you build).

## Decision
Reuse `RiskManagerPort` instead of adding `RiskGate`. `TradingOrchestrator` gains
an optional `risk_manager: RiskManagerPort | None = None` constructor parameter,
defaulting to `order_manager.risk_manager` for backward compatibility.
`_is_kill_switch_active()` delegates to `self._risk_manager` directly — no
`getattr` reach-through. The same pattern applies to the other remaining
reach-through sites (`order_placer.py`, `oms/reconciliation_service.py`,
`oms/context.py`, `services/production_readiness.py`).

## Consequences
- Positive: kill switch is compile-time wired; injected managers are honored;
  removes a silent-failure hazard on a safety-critical path.
- Negative: callers that previously relied on implicit `order_manager.risk_manager`
  resolution now pass `risk_manager` explicitly (mechanical, already defaulted).
- Cost: none — additive parameter with safe default.

## Validation
- `tests/component/trading/test_orchestrator_kill_switch_port.py`: injected
  `RiskManagerPort` is used; a different `order_manager.risk_manager` is ignored;
  no risk manager → safe `False`.
- Grep confirms no `getattr(..., "risk_manager")` in `trading_orchestrator.py`.
- import-linter: application layer still KEPT (imports only `domain.ports`).
