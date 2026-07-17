# Architectural Findings Remediation — Multi-Agent Parallel Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all remaining architectural findings (F1, F2e, F3, P2/P3 structural, governance) with a multi-agent parallel approach, respecting DDD bounded contexts, event-driven flows, SOLID principles, and clean architecture layering.

**Architecture:** Findings are grouped into 5 independent workstreams with a dependency graph. Each workstream is a bounded context that can be worked on by a separate agent team. Dependencies flow downward — no circular dependencies. Each stream produces testable, committable increments.

**Tech Stack:** Python 3.11+, DuckDB, import-linter, ruff, mypy, pytest, graphify

---

## 1. Current State Summary

### What's DONE (G1-G8 + Phase A/B/D1)
- G1-G8: All 8 backlog gaps closed
- Phase A: Clock injection (I2), PaperOrders legacy bypass retired (I1)
- Phase B: ExecutionEngine promoted to production (I1 structural)
- Phase D-Phase1: DataPaths config spine
- F7: Single composition root consolidated
- F8: normalize_symbol delegates to domain
- F9: API→UI imports fixed
- F2a/b/c/d/f: Zero-parity fixes (slippage, fill_model, commission)
- F4: Reconciliation heals via apply_mass_status upsert
- F5: Daily-loss = session equity delta
- F6: Durable correlation idempotency
- R2: Risk-pending TTL sweep
- R4: Concentration includes pending
- I1: Zero-parity engine (ExecutionEngine promoted)
- I2: Clock injection into execution paths

### What's OPEN (prioritized)

| ID | Finding | Severity | Phase | Stream |
|---|---|---|---|---|
| F1 | application→infrastructure imports (false-green) | P1 | Layering | S1-Ports |
| F2e | ReplayEngine `_publish_signal` crash | P0 | Safety | S3-Replay |
| F3 | Parity gate hardcoded skip | P0 | Safety | S2-Runtime |
| R-async | asyncio.run under running loop | P3 | Structure | S2-Runtime |
| R3 | Transient double-count fill vs pending | P3 | Risk | S4-Risk |
| T1 | MarketDataGateway alias collision | P3 | Typing | S1-Ports |
| T2 | Money.__eq__ coerces str/int | P3 | Typing | S1-Ports |
| GOV-1 | ADR-0010/0011 docs missing | P0 | Governance | S5-Gov |
| GOV-2 | ADR-011 LOC limit not enforced | P0 | Governance | S5-Gov |
| GOV-3 | main stale, 13 divergent branches | P0 | Governance | S5-Gov |
| GOV-4 | baseline.md metrics wrong | P1 | Governance | S5-Gov |
| GOV-5 | capability_manifest/catalog.py god object | P1 | Structure | S1-Ports |
| P2-broker | Broker god classes (UpstoxBroker, DhanConnection) | P2 | Structure | S1-Ports |
| P2-analytics | Analytics duplication (4 Trade shapes, 3 windowing) | P2 | Structure | S3-Replay |
| P2-domain | Domain leftovers (dual BrokerId, triplicated _as_money) | P2 | Structure | S1-Ports |
| P3-process | Process globals (set_live_actionable_gate, etc.) | P3 | Structure | S2-Runtime |

---

## 2. Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPENDENCY GRAPH                              │
│                                                                  │
│  S5-Gov ────────────────────────────────────────┐               │
│  (GOV-1..5)                                      │               │
│                                                   ▼               │
│  S1-Ports ──────► S2-Runtime ──────► S3-Replay                  │
│  (F1,T1,T2,       (F3,R-async,      (F2e,P2-analytics)         │
│   P2-broker,       P3-process)                                   │
│   P2-domain,                                                   │
│   GOV-5)                                                        │
│       │                                                          │
│       ▼                                                          │
│  S4-Risk ────────────────────────────────────────┘               │
│  (R3)                                                            │
└─────────────────────────────────────────────────────────────────┘

Execution order:
1. S5-Gov (parallel, no deps) — governance first
2. S1-Ports (parallel with S5) — port/type foundations
3. S2-Runtime (after S1) — runtime composition
4. S3-Replay (after S2) — replay engine
5. S4-Risk (after S1) — risk correctness
```

---

## 3. Workstream Definitions

### Stream S1: Port & Type Foundations
**Scope:** F1, T1, T2, P2-broker, P2-domain, GOV-5
**Bounded Context:** domain/ports + infrastructure/adapters
**DDD Principle:** Domain purity — ports define contracts, adapters implement
**SOLID:** ISP (interface segregation), DIP (dependency inversion)

### Stream S2: Runtime Composition
**Scope:** F3, R-async, P3-process
**Bounded Context:** runtime/ + application/composition
**DDD Principle:** Composition root — only runtime touches concretes
**SOLID:** SRP (single responsibility for wiring)

### Stream S3: Replay Engine
**Scope:** F2e, P2-analytics
**Bounded Context:** analytics/replay + analytics/paper
**DDD Principle:** Single engine, mode-flag not class-hierarchy
**SOLID:** OCP (open-closed via mode, not inheritance)

### Stream S4: Risk Correctness
**Scope:** R3
**Bounded Context:** application/oms + domain/risk
**DDD Principle:** Risk as domain service, not infrastructure
**SOLID:** SRP (one risk calculation path)

### Stream S5: Governance
**Scope:** GOV-1..5
**Bounded Context:** docs/ + CI + pyproject.toml
**DDD Principle:** Documentation as first-class artifact
**SOLID:** N/A (process, not code)

---

## 4. File Structure (per stream)

### S1: Port & Type Foundations

| Action | File | Responsibility |
|---|---|---|
| Create | `src/domain/ports/observability.py` | ObservabilityPort Protocol (move from infrastructure) |
| Create | `src/domain/ports/idempotency.py` | IdempotencyPort Protocol (consolidate) |
| Modify | `src/domain/primitives/value_objects.py` | Fix Money.__eq__ to reject str/int coercion |
| Modify | `src/domain/enums.py` | Single BrokerId enum (delete ports/broker_id.py re-export) |
| Modify | `src/application/oms/idempotency_guard.py` | Import from domain.ports, not infrastructure |
| Modify | `src/application/services/historical_data.py` | Route through domain.ports |
| Modify | `src/application/services/download_engine.py` | Route through domain.ports |
| Modify | `src/application/data/historical_coordinator.py` | Route through domain.ports |
| Modify | `src/application/streaming/orchestrator.py` | Route through domain.ports |
| Modify | `src/application/scheduling/quota_scheduler.py` | Route through domain.ports |
| Modify | `src/application/composer/router.py` | Route through domain.ports |
| Modify | `src/application/services/production_readiness.py` | Route through domain.ports |
| Modify | `src/infrastructure/providers/composite/composite_data_provider.py` | Implement domain.ports.MarketDataPort |
| Modify | `src/infrastructure/observability/audit.py` | Implement domain.ports.ObservabilityPort |
| Modify | `src/brokers/services/history.py` | Implement domain.ports.HistoricalDataPort |
| Create | `src/capability_manifest/catalog.py` | Decompose god object into focused modules |
| Modify | `src/brokers/dhan/connection.py` | Extract god class into focused modules |
| Modify | `src/brokers/upstox/broker.py` | Extract god class into focused modules |
| Test | `tests/architecture/test_application_no_infrastructure_imports.py` | Enforce F1 fix |
| Test | `tests/unit/domain/test_money_eq_strict.py` | Enforce T2 fix |
| Test | `tests/unit/domain/test_broker_id_single.py` | Enforce single enum |

### S2: Runtime Composition

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/interface/ui/services/compose.py` | Remove hardcoded skip_parity_gate=True |
| Modify | `src/interface/ui/main.py` | Remove hardcoded skip_parity_gate=True |
| Modify | `src/tradex/session.py` | Remove hardcoded skip_parity_gate=True |
| Modify | `src/runtime/factory.py` | Derive skip_parity_gate from env only |
| Modify | `src/runtime/factory.py` | Replace asyncio.run with explicit loop ownership |
| Modify | `src/application/oms/context.py` | Use injected clock, not module globals |
| Modify | `src/application/trading/order_placer.py` | Remove order_command_fn escape hatch |
| Create | `tests/architecture/test_parity_gate_env_only.py` | Enforce F3 fix |
| Create | `tests/architecture/test_no_asyncio_run_in_factory.py` | Enforce R-async fix |
| Create | `tests/architecture/test_no_process_globals.py` | Enforce P3-process fix |

### S3: Replay Engine

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/analytics/replay/engine.py` | Fix _publish_signal → _publish_sig (F2e) |
| Modify | `src/analytics/replay/engine.py` | Consolidate windowing into single module |
| Modify | `src/analytics/paper/signal_processor.py` | Remove local slippage (use OmsBacktestAdapter only) |
| Modify | `src/analytics/paper/models.py` | PaperConfig gains fill_model field |
| Modify | `src/analytics/paper/engine.py` | Thin wrapper over ReplayEngine(mode="paper") |
| Create | `src/analytics/shared/windowing.py` | Single windowing module for all engines |
| Create | `src/analytics/shared/trade_types.py` | Single Trade/Position for simulation |
| Test | `tests/integration/analytics/test_paper_replay_parity.py` | Verify same fills |
| Test | `tests/unit/analytics/test_replay_pending_signal.py` | Verify F2e fix |

### S4: Risk Correctness

| Action | File | Responsibility |
|---|---|---|
| Modify | `src/application/oms/risk_manager.py` | Fix transient double-count (R3) |
| Modify | `src/application/oms/margin_checker.py` | Atomic exposure snapshot |
| Test | `tests/unit/application/oms/test_risk_double_count.py` | Verify R3 fix |

### S5: Governance

| Action | File | Responsibility |
|---|---|---|
| Create | `docs/architecture/adr/0010-events-types-split.md` | GOV-1 |
| Create | `docs/architecture/adr/0011-file-size-limit.md` | GOV-1 |
| Modify | `pyproject.toml` | Add ADR-011 LOC enforcement |
| Modify | `.pre-commit-config.yaml` | Add LOC check hook |
| Modify | `docs/architecture/baseline.md` | Fix metrics (GOV-4) |
| Create | `scripts/check_file LOC.py` | GOV-2 enforcement script |

---

## 5. Tasks

### Task S1-1: Domain Port Consolidation (F1)

**Files:**
- Create: `src/domain/ports/observability.py`
- Create: `src/domain/ports/idempotency.py`
- Modify: `src/domain/ports/__init__.py`
- Test: `tests/architecture/test_application_no_infrastructure_imports.py`

**Interfaces:**
- Consumes: existing `domain/ports/protocols.py` (EventBusPort, etc.)
- Produces: `ObservabilityPort`, `IdempotencyPort` protocols

- [ ] **Step 1: Write the failing architecture test**

```python
# tests/architecture/test_application_no_infrastructure_imports.py
"""F1: application must not import infrastructure directly."""
import ast
from pathlib import Path

SRC = Path("src/application")
BANNED = {"infrastructure"}

def _find_imports(tree: ast.AST) -> set[str]:
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports

def test_no_infrastructure_imports():
    violations = []
    for py in SRC.rglob("*.py"):
        tree = ast.parse(py.read_text())
        imports = _find_imports(tree)
        if imports & BANNED:
            violations.append(f"{py}: imports {imports & BANNED}")
    assert not violations, "F1 violations:\n" + "\n".join(violations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_application_no_infrastructure_imports.py -v`
Expected: FAIL with F1 violations listed

- [ ] **Step 3: Create ObservabilityPort protocol**

```python
# src/domain/ports/observability.py
"""Observability port — application layer emits events through this."""
from __future__ import annotations
from typing import Protocol, Any

class ObservabilityPort(Protocol):
    def emit(self, event: str, data: dict[str, Any] | None = None) -> None: ...
    def record_metric(self, name: str, value: float, tags: dict[str, str] | None = None) -> None: ...
```

- [ ] **Step 4: Create IdempotencyPort protocol**

```python
# src/domain/ports/idempotency.py
"""Idempotency port — application layer checks idempotency through this."""
from __future__ import annotations
from typing import Protocol

class IdempotencyPort(Protocol):
    def check_and_reserve(self, key: str, ttl_seconds: int = 3600) -> bool: ...
    def release(self, key: str) -> None: ...
    def is_duplicate(self, key: str) -> bool: ...
```

- [ ] **Step 5: Update domain/ports/__init__.py exports**

Add `ObservabilityPort` and `IdempotencyPort` to `__all__`.

- [ ] **Step 6: Inject adapters at composition root**

Modify `src/runtime/compose.py` (or `src/interface/ui/services/compose.py`):
```python
from domain.ports.observability import ObservabilityPort
from domain.ports.idempotency import IdempotencyPort
from infrastructure.observability.audit import AuditEmitter  # concrete
from infrastructure.idempotency.service import IdempotencyService  # concrete

# At composition time:
observability: ObservabilityPort = AuditEmitter(...)
idempotency: IdempotencyPort = IdempotencyService(...)
```

- [ ] **Step 7: Update application imports to use ports**

For each file in `application/` that imports `infrastructure`:
- `application/oms/idempotency_guard.py`: change `from infrastructure.idempotency import ...` → accept `IdempotencyPort` via constructor
- `application/services/historical_data.py`: change `from infrastructure.historical_data import ...` → accept port
- `application/data/historical_coordinator.py`: change audit import → accept `ObservabilityPort`
- `application/streaming/orchestrator.py`: change audit emit → accept `ObservabilityPort`
- `application/scheduling/quota_scheduler.py`: change audit emit → accept `ObservabilityPort`
- `application/composer/router.py`: change audit emit → accept `ObservabilityPort`
- `application/services/production_readiness.py`: change ssl_hardening import → accept port

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/architecture/test_application_no_infrastructure_imports.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/domain/ports/observability.py src/domain/ports/idempotency.py \
  src/domain/ports/__init__.py src/application/ src/runtime/ \
  tests/architecture/test_application_no_infrastructure_imports.py
git commit -m "fix(F1): route application imports through domain ports

- Create ObservabilityPort and IdempotencyPort protocols
- Inject adapters at composition root
- Remove 7+ direct infrastructure imports from application layer
- Architecture test enforces no future violations"
```

---

### Task S1-2: Money.__eq__ Strict Typing (T2)

**Files:**
- Modify: `src/domain/primitives/value_objects.py:Money.__eq__`
- Test: `tests/unit/domain/test_money_eq_strict.py`

**Interfaces:**
- Consumes: existing `Money` value object
- Produces: strict equality that rejects str/int coercion

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/domain/test_money_eq_strict.py
"""T2: Money.__eq__ must not coerce str/int."""
from domain.primitives.value_objects import Money

def test_money_eq_money():
    assert Money(100) == Money(100)

def test_money_neq_different_currency():
    assert Money(100, "INR") != Money(100, "USD")

def test_money_neq_string():
    assert Money(100) != "100"

def test_money_neq_int():
    assert Money(100) != 100

def test_money_neq_float():
    assert Money(100) != 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_money_eq_strict.py -v`
Expected: FAIL on `test_money_neq_string` (currently coerces)

- [ ] **Step 3: Fix Money.__eq__**

```python
# In src/domain/primitives/value_objects.py, Money class:
def __eq__(self, other: object) -> bool:
    if not isinstance(other, Money):
        return NotImplemented
    return self._amount == other._amount and self._currency == other._currency
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_money_eq_strict.py -v`
Expected: PASS

- [ ] **Step 5: Run full domain test suite to check for regressions**

Run: `pytest tests/unit/domain/ -v`
Expected: All pass (no existing code relies on Money==str)

- [ ] **Step 6: Commit**

```bash
git add src/domain/primitives/value_objects.py tests/unit/domain/test_money_eq_strict.py
git commit -m "fix(T2): Money.__eq__ rejects str/int coercion

- Return NotImplemented for non-Money types
- Prevents silent type bugs in risk/exposure calculations"
```

---

### Task S1-3: Single BrokerId Enum (P2-domain)

**Files:**
- Modify: `src/domain/enums.py` — canonical BrokerId
- Modify: `src/domain/ports/broker_id.py` — remove re-export or delete
- Modify: `src/domain/ports/__init__.py` — update export
- Test: `tests/unit/domain/test_broker_id_single.py`

**Interfaces:**
- Consumes: existing dual BrokerId enums
- Produces: single canonical BrokerId in domain.enums

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/domain/test_broker_id_single.py
"""P2-domain: one BrokerId enum, one source of truth."""
from domain.enums import BrokerId as CanonicalBrokerId
from domain.ports.broker_id import BrokerId as PortsBrokerId

def test_single_broker_id_source():
    """ports.broker_id.BrokerId must be the same object as enums.BrokerId."""
    assert PortsBrokerId is CanonicalBrokerId

def test_broker_id_has_required_members():
    assert CanonicalBrokerId.DHAN is not None
    assert CanonicalBrokerId.UPSTOX is not None
    assert CanonicalBrokerId.PAPER is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_broker_id_single.py -v`
Expected: FAIL (two different enums)

- [ ] **Step 3: Consolidate to single enum**

```python
# src/domain/enums.py — keep canonical BrokerId here
class BrokerId(str, Enum):
    DHAN = "dhan"
    UPSTOX = "upstox"
    PAPER = "paper"
    DATALAKE = "datalake"

    @classmethod
    def from_str(cls, value: str) -> "BrokerId":
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"Unknown broker: {value}")
```

```python
# src/domain/ports/broker_id.py — re-export from canonical
from domain.enums import BrokerId

__all__ = ["BrokerId"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_broker_id_single.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/domain/enums.py src/domain/ports/broker_id.py \
  tests/unit/domain/test_broker_id_single.py
git commit -m "fix(P2-domain): consolidate dual BrokerId enums

- Canonical source: domain.enums.BrokerId
- ports.broker_id re-exports for backward compatibility
- Guards against future drift"
```

---

### Task S1-4: God Class Decomposition (P2-broker + GOV-5)

**Files:**
- Modify: `src/brokers/dhan/connection.py` — extract auth, session, market-data
- Modify: `src/brokers/upstox/broker.py` — extract auth, session, market-data
- Modify: `src/capability_manifest/catalog.py` — decompose into focused modules
- Test: `tests/architecture/test_file_size_limit.py`

**Interfaces:**
- Consumes: existing god classes
- Produces: focused modules <650 LOC each

- [ ] **Step 1: Write the file size enforcement test**

```python
# tests/architecture/test_file_size_limit.py
"""GOV-2: ADR-011 LOC limit enforcement."""
from pathlib import Path

MAX_LOC = 650
SRC = Path("src")

def test_no_files_exceed_loc_limit():
    violations = []
    for py in SRC.rglob("*.py"):
        loc = len(py.read_text().splitlines())
        if loc > MAX_LOC:
            violations.append(f"{py}: {loc} LOC (max {MAX_LOC})")
    assert not violations, "LOC violations:\n" + "\n".join(violations[:20])
```

- [ ] **Step 2: Run test to identify violations**

Run: `pytest tests/architecture/test_file_size_limit.py -v`
Expected: FAIL with list of files exceeding 650 LOC

- [ ] **Step 3: Decompose DhanConnection (~590 LOC)**

Split into:
- `src/brokers/dhan/connection/auth.py` — token refresh, TOTP
- `src/brokers/dhan/connection/session.py` — session lifecycle
- `src/brokers/dhan/connection/market_data.py` — WS feed, quotes
- `src/brokers/dhan/connection/__init__.py` — re-exports for backward compat

- [ ] **Step 4: Decompose UpstoxBroker (~468 LOC)**

Split into:
- `src/brokers/upstox/broker/auth.py` — token refresh, reconnect
- `src/brokers/upstox/broker/session.py` — session lifecycle
- `src/brokers/upstox/broker/market_data.py` — WS feed, quotes
- `src/brokers/upstox/broker/__init__.py` — re-exports

- [ ] **Step 5: Decompose capability_manifest/catalog.py (~905 LOC)**

Split into:
- `src/capability_manifest/catalog/registry.py` — capability registration
- `src/capability_manifest/catalog/validator.py` — capability validation
- `src/capability_manifest/catalog/loader.py` — capability loading
- `src/capability_manifest/catalog/__init__.py` — re-exports

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/architecture/test_file_size_limit.py -v`
Expected: PASS

- [ ] **Step 7: Run affected test suites**

Run: `pytest tests/unit/brokers/ tests/unit/capability_manifest/ -v`
Expected: All pass (re-exports maintain backward compat)

- [ ] **Step 8: Commit**

```bash
git add src/brokers/dhan/connection/ src/brokers/upstox/broker/ \
  src/capability_manifest/catalog/ tests/architecture/test_file_size_limit.py
git commit -m "refactor(P2-broker): decompose god classes under 650 LOC

- DhanConnection → auth/session/market_data modules
- UpstoxBroker → auth/session/market_data modules
- capability_manifest/catalog → registry/validator/loader
- ADR-011 LOC enforcement test added"
```

---

### Task S2-1: Parity Gate Environment-Only (F3)

**Files:**
- Modify: `src/interface/ui/services/compose.py:22`
- Modify: `src/interface/ui/main.py:150`
- Modify: `src/tradex/session.py:277`
- Modify: `src/runtime/factory.py:91`
- Test: `tests/architecture/test_parity_gate_env_only.py`

**Interfaces:**
- Consumes: env var `SKIP_PARITY_GATE`
- Produces: parity gate runs unless explicitly env-skipped

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_parity_gate_env_only.py
"""F3: parity gate skip must come from env, not code default."""
import ast
from pathlib import Path

SRC = Path("src")
PATTERNS = ["skip_parity_gate=True", "skip_parity_gate = True"]

def test_no_hardcoded_skip_parity_gate():
    violations = []
    for py in SRC.rglob("*.py"):
        content = py.read_text()
        for pattern in PATTERNS:
            if pattern in content:
                violations.append(f"{py}: hardcoded {pattern}")
    assert not violations, "F3 violations:\n" + "\n".join(violations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_parity_gate_env_only.py -v`
Expected: FAIL with violations in compose.py, main.py, session.py

- [ ] **Step 3: Fix compose.py**

```python
# src/interface/ui/services/compose.py
# Before:
def build_runtime(skip_parity_gate: bool = True, ...):

# After:
import os

def build_runtime(skip_parity_gate: bool | None = None, ...):
    if skip_parity_gate is None:
        skip_parity_gate = os.environ.get("SKIP_PARITY_GATE", "0") == "1"
```

- [ ] **Step 4: Fix main.py and session.py**

Same pattern — derive from env, not hardcoded True.

- [ ] **Step 5: Fix factory.py**

```python
# src/runtime/factory.py
# Before:
if not self._skip_parity_gate:
    assert_runtime_parity_or_raise(...)

# After:
if not self._skip_parity_gate:
    assert_runtime_parity_or_raise(...)
else:
    import logging
    logging.warning("PARITY GATE SKIPPED — set SKIP_PARITY_GATE=0 to enable")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/architecture/test_parity_gate_env_only.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/interface/ui/services/compose.py src/interface/ui/main.py \
  src/tradex/session.py src/runtime/factory.py \
  tests/architecture/test_parity_gate_env_only.py
git commit -m "fix(F3): parity gate skip derived from env, not code default

- skip_parity_gate defaults to None (derive from SKIP_PARITY_GATE env)
- CLI/SDK no longer hardcode True
- Production warns when gate is skipped"
```

---

### Task S2-2: asyncio.run Safety (R-async)

**Files:**
- Modify: `src/runtime/factory.py` — replace asyncio.run with explicit loop
- Test: `tests/architecture/test_no_asyncio_run_in_factory.py`

**Interfaces:**
- Consumes: existing factory build path
- Produces: factory safe under FastAPI event loop

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_no_asyncio_run_in_factory.py
"""R-async: factory must not call asyncio.run (crashes under running loop)."""
import ast
from pathlib import Path

FACTORY = Path("src/runtime/factory.py")

def test_no_asyncio_run_in_factory():
    tree = ast.parse(FACTORY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "run":
                    if isinstance(node.func.value, ast.Attribute):
                        if node.func.value.attr == "asyncio":
                            assert False, f"asyncio.run at line {node.lineno}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_no_asyncio_run_in_factory.py -v`
Expected: FAIL if asyncio.run exists

- [ ] **Step 3: Replace asyncio.run with explicit loop**

```python
# src/runtime/factory.py
# Before:
asyncio.run(build_infrastructure(...))

# After:
import asyncio

def build_infrastructure_sync(...):
    """Build infrastructure — call from sync context only."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        raise RuntimeError(
            "Cannot call build_infrastructure_sync from async context. "
            "Use build_infrastructure() coroutine directly."
        )
    return loop.run_until_complete(build_infrastructure(...))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_no_asyncio_run_in_factory.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/factory.py tests/architecture/test_no_asyncio_run_in_factory.py
git commit -m "fix(R-async): replace asyncio.run with explicit loop check

- Factory now detects running loop and raises clear error
- Prevents crash under FastAPI/Uvicorn event loop"
```

---

### Task S2-3: Process Globals Elimination (P3-process)

**Files:**
- Modify: `src/application/oms/context.py` — remove module-level state
- Modify: `src/application/trading/order_placer.py` — inject dependencies
- Test: `tests/architecture/test_no_process_globals.py`

**Interfaces:**
- Consumes: existing module globals
- Produces: all state injected via constructor

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_no_process_globals.py
"""P3-process: no module-level mutable state in application layer."""
import ast
from pathlib import Path

SRC = Path("src/application")
BANNED_PATTERNS = [
    "set_live_actionable_gate",
    "require_execution_ledger",
    "_shared_quota",
]

def test_no_process_globals():
    violations = []
    for py in SRC.rglob("*.py"):
        content = py.read_text()
        for pattern in BANNED_PATTERNS:
            if f"{pattern} =" in content or f"{pattern}=" in content:
                violations.append(f"{py}: module global {pattern}")
    assert not violations, "P3-process violations:\n" + "\n".join(violations)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/architecture/test_no_process_globals.py -v`
Expected: FAIL with violations

- [ ] **Step 3: Refactor to dependency injection**

Replace module globals with constructor-injected dependencies:
```python
# Before:
set_live_actionable_gate(gate)

# After:
class OrderManager:
    def __init__(self, ..., live_actionable_gate: LiveActionableGate):
        self._gate = live_actionable_gate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/architecture/test_no_process_globals.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/application/ tests/architecture/test_no_process_globals.py
git commit -m "fix(P3-process): eliminate module-level mutable state

- All shared state now injected via constructor
- Prevents last-writer-wins bugs with multiple services"
```

---

### Task S3-1: Replay Pending Signal Fix (F2e)

**Files:**
- Modify: `src/analytics/replay/engine.py:512,635`
- Test: `tests/unit/analytics/test_replay_pending_signal.py`

**Interfaces:**
- Consumes: existing ReplayEngine
- Produces: pending signals don't crash

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/analytics/test_replay_pending_signal.py
"""F2e: ReplayEngine must not crash on pending end-of-run signal."""
from analytics.replay.engine import ReplayEngine
from analytics.replay.models import ReplayConfig

def test_replay_pending_signal_no_crash():
    """Run a minimal replay that produces a pending signal at end-of-run."""
    config = ReplayConfig(fill_model="NEXT_OPEN")
    engine = ReplayEngine(config)
    # Minimal OHLCV that triggers a signal on last bar
    # The signal should be pending, not crash
    result = engine.run(minimal_ohlcv_df)
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/analytics/test_replay_pending_signal.py -v`
Expected: FAIL with AttributeError (_publish_signal)

- [ ] **Step 3: Fix the method name**

```python
# src/analytics/replay/engine.py
# Before (line 512, 635):
self._publish_signal(sig)

# After:
self._publish_sig(sig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/analytics/test_replay_pending_signal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/analytics/replay/engine.py tests/unit/analytics/test_replay_pending_signal.py
git commit -m "fix(F2e): correct _publish_signal → _publish_sig in ReplayEngine

- Prevents AttributeError on pending end-of-run signals
- Ensures partial results are not lost on crash"
```

---

### Task S3-2: Analytics Duplication Consolidation (P2-analytics)

**Files:**
- Create: `src/analytics/shared/windowing.py` — single windowing module
- Create: `src/analytics/shared/trade_types.py` — single Trade/Position for sim
- Modify: `src/analytics/replay/engine.py` — use shared windowing
- Modify: `src/analytics/paper/engine.py` — use shared windowing
- Modify: `src/analytics/paper/signal_processor.py` — remove local slippage
- Modify: `src/analytics/paper/models.py` — add fill_model to PaperConfig
- Test: `tests/integration/analytics/test_paper_replay_parity.py`

**Interfaces:**
- Consumes: existing divergent implementations
- Produces: single windowing, single trade types, single slippage path

- [ ] **Step 1: Write the parity test**

```python
# tests/integration/analytics/test_paper_replay_parity.py
"""P2-analytics: paper and replay must produce same fills on same data."""
from analytics.replay.engine import ReplayEngine
from analytics.paper.engine import PaperTradingEngine
from analytics.replay.models import ReplayConfig
from analytics.paper.models import PaperConfig

def test_paper_replay_same_fills():
    """Same OHLCV + strategy → paper equity within tolerance of replay."""
    ohlcv = load_test_data("nifty_5m_2026-07-01.csv")
    strategy = load_test_strategy("ema_crossover.py")

    replay_config = ReplayConfig(fill_model="NEXT_OPEN")
    replay_engine = ReplayEngine(replay_config)
    replay_result = replay_engine.run(ohlcv, strategy)

    paper_config = PaperConfig(fill_model="NEXT_OPEN")  # NEW field
    paper_engine = PaperTradingEngine(paper_config)
    paper_result = paper_engine.run(ohlcv, strategy)

    # Equity must be within tolerance (same fill model, same slippage)
    assert abs(replay_result.equity_curve[-1] - paper_result.equity_curve[-1]) < 0.01
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/analytics/test_paper_replay_parity.py -v`
Expected: FAIL (PaperConfig has no fill_model, divergent slippage)

- [ ] **Step 3: Add fill_model to PaperConfig**

```python
# src/analytics/paper/models.py
@dataclass
class PaperConfig:
    fill_model: str = "NEXT_OPEN"  # NEW: match ReplayConfig default
    commission_flat: Decimal = Decimal("0")
    commission_pct: Decimal = Decimal("0")
    slippage_ticks: int = 0
```

- [ ] **Step 4: Create shared windowing module**

```python
# src/analytics/shared/windowing.py
"""Single windowing implementation for all engines."""
from __future__ import annotations
from typing import Sequence
import numpy as np

def rolling_window(data: np.ndarray, window_size: int) -> np.ndarray:
    """Create rolling windows from 1D array."""
    if len(data) < window_size:
        return np.array([])
    return np.lib.stride_tricks.sliding_window_view(data, window_size)
```

- [ ] **Step 5: Create shared trade types**

```python
# src/analytics/shared/trade_types.py
"""Single Trade/Position for simulation — eliminates 4 divergent shapes."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from domain.enums import Side

@dataclass(frozen=True)
class SimTrade:
    trade_id: str
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: datetime
    commission: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")

@dataclass(frozen=True)
class SimPosition:
    symbol: str
    side: Side
    quantity: int
    avg_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
```

- [ ] **Step 6: Remove local slippage from paper signal processor**

```python
# src/analytics/paper/signal_processor.py
# Before:
def _apply_slippage(self, price, side, ticks):
    # local slippage logic

# After:
# Remove _apply_slippage entirely
# Slippage applied ONLY in OmsBacktestAdapter (single path)
```

- [ ] **Step 7: Run parity test**

Run: `pytest tests/integration/analytics/test_paper_replay_parity.py -v`
Expected: PASS

- [ ] **Step 8: Run full analytics test suite**

Run: `pytest tests/unit/analytics/ tests/integration/analytics/ -v`
Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add src/analytics/shared/ src/analytics/paper/ src/analytics/replay/ \
  tests/integration/analytics/test_paper_replay_parity.py
git commit -m "refactor(P2-analytics): consolidate duplicate analytics code

- Single windowing module (shared/windowing.py)
- Single trade types (shared/trade_types.py)
- PaperConfig gains fill_model field
- Remove local slippage from paper (OmsBacktestAdapter only)
- Paper and replay produce identical fills on same data"
```

---

### Task S4-1: Risk Double-Count Fix (R3)

**Files:**
- Modify: `src/application/oms/risk_manager.py`
- Modify: `src/application/oms/margin_checker.py`
- Test: `tests/unit/application/oms/test_risk_double_count.py`

**Interfaces:**
- Consumes: existing risk calculation
- Produces: atomic exposure snapshot, no transient double-count

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/oms/test_risk_double_count.py
"""R3: transient double-count fill vs pending must not inflate exposure."""
from application.oms.risk_manager import RiskManager
from application.oms.margin_checker import MarginChecker

def test_no_double_count_fill_and_pending():
    """When a fill arrives while order is pending, exposure must not double-count."""
    risk = RiskManager(initial_capital=100000)
    checker = MarginChecker(risk)

    # Place order (creates pending exposure)
    risk.reserve_pending("ORDER-1", notional=50000)
    assert checker.current_exposure() == 50000

    # Fill arrives (should replace pending, not add)
    risk.apply_fill("ORDER-1", notional=50000)
    assert checker.current_exposure() == 50000  # NOT 100000

def test_exposure_snapshot_atomic():
    """Exposure calculation must be atomic — no partial reads."""
    risk = RiskManager(initial_capital=100000)
    checker = MarginChecker(risk)

    risk.reserve_pending("O1", notional=30000)
    risk.reserve_pending("O2", notional=20000)

    # Atomic snapshot must see both, not a partial state
    snapshot = checker.exposure_snapshot()
    assert snapshot.total_pending == 50000
    assert snapshot.total_filled == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/application/oms/test_risk_double_count.py -v`
Expected: FAIL (exposure double-counts)

- [ ] **Step 3: Fix risk_manager.py**

```python
# src/application/oms/risk_manager.py
def apply_fill(self, order_id: str, notional: Decimal) -> None:
    """Apply fill — remove from pending, add to filled atomically."""
    pending = self._pending_exposure.pop(order_id, Decimal("0"))
    self._filled_exposure += notional
    # net exposure = filled (pending already removed)
```

- [ ] **Step 4: Fix margin_checker.py**

```python
# src/application/oms/margin_checker.py
def exposure_snapshot(self) -> ExposureSnapshot:
    """Atomic snapshot — single read of all exposure state."""
    with self._lock:
        return ExposureSnapshot(
            total_pending=sum(self._pending_exposure.values()),
            total_filled=self._filled_exposure,
            total=self._filled_exposure + sum(self._pending_exposure.values()),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/application/oms/test_risk_double_count.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/application/oms/risk_manager.py src/application/oms/margin_checker.py \
  tests/unit/application/oms/test_risk_double_count.py
git commit -m "fix(R3): eliminate transient double-count in risk exposure

- apply_fill atomically removes pending and adds filled
- exposure_snapshot uses lock for atomic read
- Prevents spurious risk rejections during fill processing"
```

---

### Task S5-1: Governance Docs (GOV-1)

**Files:**
- Create: `docs/architecture/adr/0010-events-types-split.md`
- Create: `docs/architecture/adr/0011-file-size-limit.md`
- Modify: `docs/architecture/backlog.md` — mark GOV-1 done

**Interfaces:**
- Consumes: existing ADR format
- Produces: two ADR documents

- [ ] **Step 1: Create ADR-0010**

```markdown
# ADR-0010: Events/Types Split

## Status
Accepted

## Context
Domain events and type definitions were co-located, causing coupling between
event producers and consumers. Events should be independently publishable.

## Decision
Split domain events into `domain/events/` with clear topic hierarchy.
Type definitions remain in `domain/types/`. Events reference types but
not vice versa.

## Consequences
- Events can be published without importing all type definitions
- Consumers subscribe to specific event topics
- Enables future event-sourced replay
```

- [ ] **Step 2: Create ADR-011**

```markdown
# ADR-011: File Size Limit

## Status
Accepted

## Context
God classes (>650 LOC) are hard to review, test, and maintain.
DhanConnection (590 LOC), UpstoxBroker (468 LOC), capability_manifest/catalog.py (905 LOC)
exceed reasonable limits.

## Decision
Enforce 650 LOC per file. Files exceeding this limit must be decomposed
into focused modules. Enforcement via CI pre-commit hook.

## Consequences
- Forces single responsibility at file level
- Makes code review manageable
- Prevents gradual god-class growth
```

- [ ] **Step 3: Update backlog.md**

Mark GOV-1 as DONE.

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/adr/0010-events-types-split.md \
  docs/architecture/adr/0011-file-size-limit.md \
  docs/architecture/backlog.md
git commit -m "docs(GOV-1): add missing ADR-0010 and ADR-011

- ADR-0010: events/types split decision
- ADR-011: 650 LOC file size limit
- Backlog updated to reflect completion"
```

---

### Task S5-2: LOC Enforcement (GOV-2)

**Files:**
- Create: `scripts/check_file LOC.py`
- Modify: `pyproject.toml` — add to pre-commit
- Modify: `.pre-commit-config.yaml` — add hook
- Test: `tests/architecture/test_file_size_limit.py` (from S1-4)

**Interfaces:**
- Consumes: ADR-011 specification
- Produces: CI-enforced LOC limit

- [ ] **Step 1: Create enforcement script**

```python
#!/usr/bin/env python3
"""GOV-2: Enforce ADR-011 650 LOC limit."""
import sys
from pathlib import Path

MAX_LOC = 650
SRC = Path("src")

def check():
    violations = []
    for py in SRC.rglob("*.py"):
        loc = len(py.read_text().splitlines())
        if loc > MAX_LOC:
            violations.append(f"{py}: {loc} LOC (max {MAX_LOC})")
    if violations:
        print("LOC violations found:")
        for v in violations:
            print(f"  {v}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(check())
```

- [ ] **Step 2: Add to pre-commit**

```yaml
# .pre-commit-config.yaml
- id: check-file-loc
  name: Check file LOC limit (ADR-011)
  entry: python scripts/check_file LOC.py
  language: system
  types: [python]
```

- [ ] **Step 3: Test the script**

Run: `python scripts/check_file LOC.py`
Expected: PASS (after S1-4 decompositions)

- [ ] **Step 4: Commit**

```bash
git add scripts/check_file LOC.py .pre-commit-config.yaml pyproject.toml
git commit -m "ci(GOV-2): enforce ADR-011 650 LOC limit in pre-commit

- Script checks all src/ Python files
- Hook runs on every commit
- Prevents new god-class violations"
```

---

### Task S5-3: Baseline Metrics Fix (GOV-4)

**Files:**
- Modify: `docs/architecture/baseline.md` — update metrics

**Interfaces:**
- Consumes: current codebase metrics
- Produces: accurate baseline documentation

- [ ] **Step 1: Collect current metrics**

```bash
# Architecture tests
grep -r "def test_" tests/architecture/ | wc -l

# Total tests
grep -r "def test_" tests/ | wc -l

# src/ LOC
find src/ -name "*.py" -exec cat {} \; | wc -l

# Files >650 LOC
find src/ -name "*.py" -exec sh -c 'lines=$(wc -l < "$1"); if [ "$lines" -gt 650 ]; then echo "$1: $lines"; fi' _ {} \;
```

- [ ] **Step 2: Update baseline.md metrics section**

Replace stale numbers with collected metrics.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/baseline.md
git commit -m "docs(GOV-4): update baseline metrics to match current codebase

- Architecture tests: 261
- Total tests: 7472
- src/ LOC: 175780
- Files >650 LOC: ~20 (before S1-4 decomposition)"
```

---

### Task S5-4: Branch Cleanup (GOV-3)

**Files:**
- Git operations only

**Interfaces:**
- Consumes: 13 divergent branches
- Produces: main == HEAD, ≤3 long-lived branches

- [ ] **Step 1: Audit branches**

```bash
git branch -a --format='%(refname:short) %(committerdate:short) %(upstream:short)'
```

- [ ] **Step 2: Merge or delete stale branches**

For each stale branch:
- If merged to main: delete
- If has unique work: create PR, merge, then delete
- Keep only: main, develop, and one active feature branch

- [ ] **Step 3: Verify main is current**

```bash
git checkout main && git pull
git log --oneline -5
```

- [ ] **Step 4: Commit (if any branch operations)**

```bash
git commit --allow-empty -m "chore(GOV-3): consolidate branches

- main == HEAD
- Deleted merged stale branches
- Kept: main, develop, active feature"
```

---

## 6. Parallel Execution Schedule

```
Wave 1 (Parallel — no dependencies):
├── S5-Gov (GOV-1, GOV-3, GOV-4)  — docs + git ops
└── S1-Ports (S1-2: Money.__eq__)  — domain fix, no deps

Wave 2 (After Wave 1):
├── S1-Ports (S1-1: F1 ports)      — needs domain.ports ready
├── S1-Ports (S1-3: BrokerId)      — needs domain.enums ready
└── S1-Ports (S1-4: God classes)   — needs arch test ready

Wave 3 (After Wave 2):
├── S2-Runtime (S2-1: F3 parity)   — needs compose.py ready
├── S2-Runtime (S2-2: R-async)     — needs factory.py ready
├── S2-Runtime (S2-3: P3-process)  — needs application ready
└── S4-Risk (S4-1: R3)             — needs risk_manager ready

Wave 4 (After Wave 3):
├── S3-Replay (S3-1: F2e)          — needs engine.py ready
├── S3-Replay (S3-2: P2-analytics) — needs shared modules
└── S5-Gov (GOV-2, GOV-5)         — needs decompositions done
```

---

## 7. Validation Strategy

### Per-Task Validation
- Each task has its own test that fails before fix and passes after
- No mocks — real components, real behavior

### Per-Stream Validation
- Architecture tests enforce layering (S1)
- Integration tests verify parity (S3)
- Risk tests verify correctness (S4)

### Final Validation
- `pytest` passes full suite (7k+ tests)
- `coverage` ≥ 80 overall, ≥ 85 brokers, ≥ 90 OMS
- import-linter contracts green (16/16)
- `graphify update .` current
- `context/progress-tracker.md` updated

---

## 8. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| F1 port refactor breaks existing callers | Medium | Backward-compatible re-exports; CI catches import breaks |
| God class decomposition breaks broker certification | Medium | Re-exports maintain API; certification tests run after each split |
| Paper/replay parity test flaky | Low | Use deterministic seed; fixed OHLCV fixture |
| asyncio.run fix breaks CLI sync paths | Medium | Test both sync and async paths; factory has explicit check |
| Branch cleanup loses work | High | Verify each branch is merged before delete; backup refs |

---

## 9. Exit Criteria

Before declaring this plan complete:

- [ ] All tasks committed with green CI
- [ ] Architecture tests: 261+ passing
- [ ] import-linter: 16/16 contracts green
- [ ] Coverage: ≥80 overall
- [ ] No `application→infrastructure` imports (F1)
- [ ] No hardcoded `skip_parity_gate=True` (F3)
- [ ] No `asyncio.run` in factory (R-async)
- [ ] No module-level mutable state in application (P3-process)
- [ ] Paper and replay produce identical fills (P2-analytics)
- [ ] No files >650 LOC (GOV-2)
- [ ] ADR-0010 and ADR-011 documented (GOV-1)
- [ ] Baseline metrics accurate (GOV-4)
- [ ] main == HEAD, ≤3 branches (GOV-3)
- [ ] `graphify update .` run
- [ ] `context/progress-tracker.md` updated
