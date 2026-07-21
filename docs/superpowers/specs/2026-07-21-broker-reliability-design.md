# Broker Subsystem Reliability — Design Spec

> Principal Engineering Plan: Transform "structurally good, behaviorally fragile" → "structurally clean AND behaviorally reliable"

## Problem

Architecture is design-grade (OCP/DIP/ISP at domain boundary) but runtime-unreliable:
- Structural contracts exist; behavioral contracts don't
- Error taxonomy exists; many paths bypass it
- Plugin system exists; session lifecycle doesn't respect it
- Resilience primitives exist; wiring is inconsistent

## Approach

Layer-by-layer with safety gates. Each phase produces shippable software.

## Phases

### Phase 0: Emergency P0 — Money Safety (Week 1-2)
- API async cancel/modify sync bridge
- Paper success flag on REJECTED
- disclosed_quantity TypeError
- Idempotency reservation after ambiguous POST
- Upstox CB on 4xx
- cancel_all_orders error masking
- Token JSON out of source tree

**Gate:** Every order path yields correct `OrderResponse.success` and OMS state.

### Phase 1: Session Lifecycle (Week 2-3)
- Gateway cache + lifecycle reconnect
- Failed probe registry poisoning
- CLI session opener wiring
- FSM state derivation
- Close subscription teardown
- Upstox WS exhausted reset + reconnect

**Gate:** connect → use → close → reconnect works for all brokers.

### Phase 2: Behavioral LSP — Contract Parity (Week 3-5)
- Upstox unmapped status fail-closed
- Paper cancel/modify OMS sync
- Paper partial market fills
- Quote/LTP zero-defaults rejection
- History gap detection
- Dhan modify wire payload
- Upstox cancel fill-race check

**Gate:** All brokers produce identical postconditions.

### Phase 3: DIP + Protocol Alignment (Week 5-6)
- Brokers use EventBusPort not concrete EventBus
- Legacy MarketDataProvider elimination
- PaperGateway Any → explicit protocols
- God constructor extraction
- ExecutionComposer asyncio.run fix

**Gate:** Zero infrastructure imports in brokers.

### Phase 4: Cross-Cutting Reliability (Week 6-7)
- Central idempotency with UNKNOWN state
- Single rate-limit authority
- Token expiry event subscribers
- End-to-end correlation
- Adaptive rate recovery
- Dhan token broadcast to WS

**Gate:** Every write path has consistent resilience.

### Phase 5: Observability + Hardening (Week 7-8)
- Hard cert probes
- Capability enforcement
- Multi-account scoping
- Naive datetime cleanup

**Gate:** Live ADR readiness ≥8.5.

## Non-Goals (YAGNI)
- Physical package restructuring
- @final decorators
- Multi-account first-class (deferred)
- BrokerAdapter union split (intentional)
