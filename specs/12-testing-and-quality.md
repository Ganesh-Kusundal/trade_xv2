# 12 — Testing and Quality

## 1. Purpose

Quality is enforced through a test pyramid, architecture contracts, and parity gates. The system trades real money; tests must verify correctness across all environments without mocks for core trading logic.

## 2. Test Pyramid

```
                    ┌─────────┐
                    │   E2E   │  Full session flows
                   ┌┴─────────┴┐
                   │ Integration │  Broker adapters, datalake
                  ┌┴─────────────┴┐
                  │  Component     │  OMS, execution, risk
                 ┌┴───────────────┴┐
                 │     Unit         │  Domain, messages, FSM
                 └───────────────────┘
```

| Layer | Scope | Target Share | Examples |
|-------|-------|--------------|----------|
| Unit | Pure domain logic, FSM, messages, lifecycle | ~70% | Order FSM, ComponentState transitions, RiskRule logic |
| Component | Single subsystem with real deps | ~15% | ExecutionEngine + SimulatedFillSource, MessageBus routing |
| Integration | Cross-subsystem with real broker sandbox | ~10% | Dhan adapter place/cancel, datalake roundtrip |
| E2E | Full session flows | ~5% | Replay → backtest → paper session |
| Architecture | Layer boundaries, flow contracts, graph degree | CI-blocking | Import linter, god-class degree ≤ 50, bypass scan |

## 3. Four-Mode Parity Tests

### Parity Gate

The parity gate verifies identical behavior across all four modes:

```python
def test_order_fsm_four_mode_parity():
    """Same order FSM transitions in REPLAY, BACKTEST, PAPER, LIVE."""
    for mode in [Mode.REPLAY, Mode.BACKTEST, Mode.PAPER, Mode.LIVE]:
        engine = build_engine(mode)
        result = engine.submit(test_order_command)
        assert result.status == OrderStatus.SUBMITTED
```

### Parity Rules

| Rule | Test |
|------|------|
| Same ExecutionEngine code | Import path identical across modes |
| Same RiskEngine code | Risk check produces same result given same context |
| Same Order FSM | All transitions tested identically |
| Same FeaturePipeline | Features computed identically given same bars |
| FillSource differs only | Replay/Simulated/Paper/Broker are the only delta |
| No bypass paths | Architecture test: zero alternate order paths |
| Parity gate never skipped in LIVE | LIVE mode rejects SKIP_PARITY_GATE |
| Replay determinism | MessageLog replay → identical cache snapshot |

## 4. AdapterTestHarness

Standardized test harness for broker adapter validation:

```python
class AdapterTestHarness:
    def __init__(self, adapter: BrokerAdapter): ...

    def test_connect(self) -> None: ...
    def test_get_quote(self, instrument_id: InstrumentId) -> None: ...
    def test_place_and_cancel(self, command: OrderCommand) -> None: ...
    def test_get_positions(self) -> None: ...
    def test_get_funds(self) -> None: ...
    def test_mass_status(self) -> None: ...
    def test_streaming(self, instrument_id: InstrumentId) -> None: ...
    def test_reconciliation(self) -> None: ...
    def test_wire_mapping_roundtrip(self) -> None: ...
```

Each broker plugin must pass AdapterTestHarness against its sandbox environment.

## 5. Flow Contract Tests

Architecture tests verify flow contract markers exist:

| Flow | Required Contract Sections |
|------|---------------------------|
| §1 Startup | Boot checks, environment freeze |
| §6 Quote | Cache-then-publish invariant |
| §7 Order | Idempotency → Risk → Execution spine |
| §9 Reconciliation | Drift severity, heal rules |
| §11 Mode | Environment matrix, parity invariant |

## 6. Architecture Quality Gates

### Import Boundary Contracts

| Contract | Rule |
|----------|------|
| Domain purity | domain imports nothing from outer layers |
| Application isolation | application imports only domain |
| Runtime exclusivity | only runtime imports concrete brokers |
| Strategy isolation | strategies cannot import OMS/execution |
| Trading without strategies | OMS + execution testable with zero strategies |

### Dependency Graph

```
interface → runtime → infrastructure + application + plugins
infrastructure → application → domain
application → domain
domain → (nothing inward)
plugins → domain
```

Approved debt edges (application → infrastructure) are explicitly listed and limited.

## 7. Key Test Patterns

### Order FSM Test

```python
def test_order_fsm_transitions():
    om = OrderManager()
    order = om.create(test_command)
    assert order.status == OrderStatus.PENDING
    om.transition(order.id, OrderStatus.SUBMITTED)
    assert order.status == OrderStatus.SUBMITTED
    om.transition(order.id, OrderStatus.FILLED)
    assert order.status == OrderStatus.FILLED
    with pytest.raises(IllegalTransition):
        om.transition(order.id, OrderStatus.PENDING)
```

### Idempotency Test

```python
def test_duplicate_correlation_returns_prior():
    guard = IdempotencyGuard()
    cid = CorrelationId(uuid4())
    guard.check_and_reserve(cid)
    result1 = submit_order(cid)
    guard.record_result(cid, result1)
    result2 = submit_order(cid)  # same correlation_id
    assert result2 == result1
```

### Risk Gate Test

```python
def test_risk_rejected_never_reaches_venue():
    risk = RiskManager(config_with_low_limit)
    venue = RecordingVenue()
    engine = ExecutionEngine(risk=risk, fill_source=venue)
    engine.submit(oversized_order)
    assert venue.submissions == []  # no venue call
    assert published_events includes RiskRejected
```

### Reconciliation Test

```python
def test_high_drift_triggers_heal():
    local = [order_qty_100]
    broker = [order_qty_200]  # mismatch
    drifts = ReconciliationEngine.compare_orders(local, broker)
    assert any(d.severity == DriftSeverity.HIGH for d in drifts)
```

## 8. Test Markers

| Marker | Purpose |
|--------|---------|
| @pytest.mark.live | Requires live broker credentials |
| @pytest.mark.integration | Requires external services |
| @pytest.mark.slow | Long-running tests |
| @pytest.mark.parity | Zero-parity gate tests |

Default test run excludes live and integration markers (offline-safe).

## 9. Mutation Testing

Critical paths subject to mutation testing:

- Order FSM transition logic
- RiskGate check_order
- IdempotencyGuard check_and_reserve
- ReconciliationEngine.compare_orders

Mutants that survive indicate missing test coverage.

## 10. CI Pipeline Stages

| Stage | Tests | Gate |
|-------|-------|------|
| Lint | ruff, mypy | Zero errors |
| Unit | Domain, FSM, messages | All pass |
| Component | OMS, execution, risk | All pass |
| Architecture | Import linter, flow contracts | All pass |
| Integration | Broker sandbox, datalake | All pass (nightly) |
| Parity | Four-mode parity gate | All pass |
| Replay | Deterministic replay test | All pass (nightly) |
| E2E | Full session flows | All pass (nightly) |

### Forbidden Bypass Test

```python
def test_no_bypass_order_path():
    """No alternate order path outside ExecutionEngine."""
    assert bypass_paths == []

def test_no_god_classes():
    """No class exceeds max dependency degree."""
    assert all(degree <= 50 for degree in dependency_degrees)
```

## 11. Quality Invariants

1. No mocked components in integration or E2E tests
2. Four-mode parity gate runs on every CI build
3. LIVE parity gate cannot be skipped
4. No bypass order paths — architecture test enforced
5. Architecture tests are CI-blocking
6. AdapterTestHarness required for every venue plugin
7. Flow contract markers verified by architecture tests
8. Replay determinism test: log replay → identical cache
9. Mutation testing on critical trading paths
