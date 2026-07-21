# Ponytail Audit Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 14 over-engineering findings from the ponytail audit, removing ~400-600 lines of redundant code.

**Architecture:** Five independent parallel streams, each tackling a cluster of related findings. No cross-stream dependencies until final integration.

**Tech Stack:** Python 3.12+, dataclasses, Protocol, ABC

## Global Constraints

- Preserve all public APIs — no breaking changes for external consumers
- Maintain test coverage — run `pytest tests/` after each stream
- Follow existing code conventions (see `context/code-standards.md`)
- Each stream produces a working, testable state

---

## Parallel Execution Map

```
Stream A: Protocol Cleanup (Findings #1, #2)     ─┐
Stream B: ABC Simplification (Findings #4, #5)    ─┼─→ Final Integration
Stream C: Mixin Consolidation (Finding #6)        ─┤
Stream D: Generic Registry (Finding #7)           ─┤
Stream E: Health & Misc Cleanup (#3, #8-14)       ─┘
```

---

## Stream A: Protocol Cleanup

### Task A1: Consolidate ManagedService Protocol

**Files:**
- Modify: `src/domain/ports/lifecycle.py` (keep as canonical)
- Modify: `src/infrastructure/lifecycle/lifecycle.py` (import from domain, delete local definition)
- Modify: `src/brokers/providers/dhan/data/depth_feed_base/__init__.py` (update import)

**Interfaces:**
- Consumes: None
- Produces: Single `ManagedServicePort` protocol in `domain.ports.lifecycle`

- [ ] **Step 1: Update infrastructure import**

```python
# src/infrastructure/lifecycle/lifecycle.py
# Replace the local ManagedService protocol with import from domain
from domain.ports.lifecycle import ManagedServicePort as ManagedService
```

- [ ] **Step 2: Update depth_feed_base import**

```python
# src/brokers/providers/dhan/data/depth_feed_base/__init__.py
# Change: from infrastructure.lifecycle.lifecycle import ManagedService
# To:     from domain.ports.lifecycle import ManagedServicePort as ManagedService
```

- [ ] **Step 3: Remove duplicate protocol definition**

Delete the `ManagedService` class definition from `src/infrastructure/lifecycle/lifecycle.py` (lines 33-50).

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add src/domain/ports/lifecycle.py src/infrastructure/lifecycle/lifecycle.py src/brokers/providers/dhan/data/depth_feed_base/__init__.py
git commit -m "refactor: consolidate ManagedService protocol to domain.ports.lifecycle"
```

---

### Task A2: Remove Duplicate FieldMapping Protocol

**Files:**
- Verify: `src/infrastructure/mappers/order_mapper.py` (check if alias is used)
- Modify: Remove alias if unused

**Interfaces:**
- Consumes: None
- Produces: Single `FieldMapping` in `domain.entities.order`

- [ ] **Step 1: Check usage of mapper FieldMapping**

```bash
grep -r "from infrastructure.mappers.order_mapper import FieldMapping" src/
```

- [ ] **Step 2: If no imports, delete alias**

```python
# Remove from src/infrastructure/mappers/order_mapper.py:
# class FieldMapping(Protocol):  # pragma: no cover - back-compat alias
#     ...
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/mappers/order_mapper.py
git commit -m "refactor: remove duplicate FieldMapping protocol alias"
```

---

## Stream B: ABC Simplification

### Task B1: Simplify Cache ABC

**Files:**
- Modify: `src/infrastructure/cache.py`

**Interfaces:**
- Consumes: None
- Produces: `Cache` class (formerly `MemoryCache`)

- [ ] **Step 1: Remove ABC, rename MemoryCache to Cache**

```python
# src/infrastructure/cache.py
# Remove: class Cache(ABC): ...
# Rename: class MemoryCache(Cache): → class Cache:
```

- [ ] **Step 2: Update module exports**

```python
# Update __all__ or public API if exists
# Update memory_cache = Cache()  (was MemoryCache())
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/cache.py
git commit -m "refactor: simplify Cache by removing unnecessary ABC"
```

---

### Task B2: Simplify AuditStore ABC

**Files:**
- Modify: `src/application/audit.py`

**Interfaces:**
- Consumes: None
- Produces: Concrete `MemoryAuditStore` and `FileAuditStore` (keep both)

- [ ] **Step 1: Remove ABC base class**

```python
# src/application/audit.py
# Remove: from abc import ABC, abstractmethod
# Remove: class AuditStore(ABC): ...
# Keep: MemoryAuditStore and FileAuditStore as standalone classes
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add src/application/audit.py
git commit -m "refactor: remove AuditStore ABC, keep concrete implementations"
```

---

## Stream C: Mixin Consolidation

### Task C1: Merge Instrument Mixins

**Files:**
- Modify: `src/domain/instruments/instrument_market_data.py`
- Modify: `src/domain/instruments/instrument_streaming.py`
- Modify: `src/domain/instruments/instrument_trading.py`
- Create: `src/domain/instruments/instrument_mixin.py` (merged)
- Modify: `src/domain/instruments/instrument.py` (update imports)

**Interfaces:**
- Consumes: None
- Produces: Single `InstrumentMixin` class

- [ ] **Step 1: Create merged InstrumentMixin**

```python
# src/domain/instruments/instrument_mixin.py
"""Consolidated instrument mixins — market data, streaming, and trading."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.instruments.instrument import Instrument


class InstrumentMixin:
    """All instrument convenience methods in one place."""
    
    # Market data methods from instrument_market_data.py
    # Streaming methods from instrument_streaming.py  
    # Trading methods from instrument_trading.py
```

- [ ] **Step 2: Move methods from each mixin into InstrumentMixin**

- [ ] **Step 3: Update instrument.py imports**

```python
# src/domain/instruments/instrument.py
# Change: from domain.instruments.instrument_market_data import InstrumentMarketDataMixin
#         from domain.instruments.instrument_streaming import InstrumentStreamingMixin
#         from domain.instruments.instrument_trading import InstrumentTradingMixin
# To:     from domain.instruments.instrument_mixin import InstrumentMixin
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add src/domain/instruments/
git commit -m "refactor: consolidate 3 instrument mixins into single InstrumentMixin"
```

---

### Task C2: Merge Session Mixins

**Files:**
- Modify: `src/domain/_session_trading.py`
- Modify: `src/domain/_session_instruments.py`
- Create: `src/domain/_session_mixin.py` (merged)
- Modify: `src/domain/session.py` (update imports)

**Interfaces:**
- Consumes: None
- Produces: Single `SessionMixin` class

- [ ] **Step 1: Create merged SessionMixin**

```python
# src/domain/_session_mixin.py
"""Consolidated session mixin — trading and instrument resolution."""

from __future__ import annotations

class SessionMixin:
    """All session convenience methods in one place."""
    
    # Trading methods from _session_trading.py
    # Instrument methods from _session_instruments.py
```

- [ ] **Step 2: Move methods from each mixin**

- [ ] **Step 3: Update session.py**

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add src/domain/_session_*.py src/domain/session.py
git commit -m "refactor: consolidate session trading + instrument mixins"
```

---

## Stream D: Generic Registry

### Task D1: Create Generic Registry Base

**Files:**
- Create: `src/domain/registry.py` (generic base)
- Modify: Multiple registry classes to inherit from base

**Interfaces:**
- Consumes: None
- Produces: `Registry[T]` generic base class

- [ ] **Step 1: Create generic Registry[T]**

```python
# src/domain/registry.py
"""Generic registry base class."""

from __future__ import annotations
from typing import TypeVar, Generic, overload

T = TypeVar("T")

class Registry(Generic[T]):
    """Base registry with register/get/has/keys/values/items."""
    
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
    
    def register(self, name: str, item: T) -> None:
        self._items[name] = item
    
    def get(self, name: str) -> T | None:
        return self._items.get(name)
    
    def has(self, name: str) -> bool:
        return name in self._items
    
    def keys(self) -> list[str]:
        return list(self._items.keys())
    
    def values(self) -> list[T]:
        return list(self._items.values())
    
    def items(self) -> list[tuple[str, T]]:
        return list(self._items.items())
    
    def __len__(self) -> int:
        return len(self._items)
    
    def __contains__(self, name: str) -> bool:
        return self.has(name)
```

- [ ] **Step 2: Migrate simple registries (PatternRegistry, ViewRegistry, etc.)**

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/domain/registry.py
git commit -m "feat: add generic Registry[T] base class"
```

---

## Stream E: Health & Misc Cleanup

### Task E1: Simplify Health Types

**Files:**
- Modify: `src/infrastructure/health.py`

**Interfaces:**
- Consumes: None
- Produces: Simplified health types

- [ ] **Step 1: Merge HealthResult into HealthStatus or simplify**

```python
# src/infrastructure/health.py
# Consider: HealthResult → HealthStatus with optional details dict
# Remove: separate HealthCheck ABC if only 1-2 implementations
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add src/infrastructure/health.py
git commit -m "refactor: simplify health check types"
```

---

### Task E2: Remove Back-Compat Re-Export

**Files:**
- Modify: `src/infrastructure/lifecycle/lifecycle.py`

**Interfaces:**
- Consumes: None
- Produces: Cleaner module exports

- [ ] **Step 1: Check if build_health re-export is used**

```bash
grep -r "from infrastructure.lifecycle.lifecycle import build_health" src/
```

- [ ] **Step 2: If unused, remove re-export**

```python
# Remove from src/infrastructure/lifecycle/lifecycle.py line 211:
# from domain.lifecycle_health import build_health  # noqa: F401, E402 — re-export for backward compat
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/lifecycle/lifecycle.py
git commit -m "refactor: remove unused build_health re-export"
```

---

### Task E3: Use OrderedDict in MemoryCache

**Files:**
- Modify: `src/infrastructure/cache.py`

**Interfaces:**
- Consumes: Cache class from Task B1
- Produces: Simpler LRU implementation

- [ ] **Step 1: Replace insertion tracking with OrderedDict**

```python
# src/infrastructure/cache.py
from collections import OrderedDict

class Cache:
    def __init__(self, default_ttl: int = 300, maxsize: int = 10_000) -> None:
        self._default_ttl = default_ttl
        self._maxsize = maxsize
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        # Remove: _insertion_counter, _insertion_order
```

- [ ] **Step 2: Update eviction to use move_to_end**

```python
def _evict_oldest(self) -> None:
    while len(self._store) > self._maxsize:
        self._store.popitem(last=False)  # Remove oldest
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -x -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/infrastructure/cache.py
git commit -m "refactor: use OrderedDict for simpler LRU cache eviction"
```

---

## Final Integration

### Task F1: Cross-Stream Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

- [ ] **Step 2: Run type checks**

```bash
mypy src/ --ignore-missing-imports
```

- [ ] **Step 3: Run linter**

```bash
ruff check src/
```

- [ ] **Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address integration issues from ponytail audit remediation"
```

---

## Success Metrics

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Protocol definitions | 2 (ManagedService) | 1 | -1 |
| ABC classes | 3 (Cache, AuditStore, HealthCheck) | 1 (HealthCheck) | -2 |
| Mixin classes | 7 | 3 | -4 |
| Lines of code | ~400 redundant | 0 | -400 |
| Registry boilerplate | ~100 lines duplicated | ~20 lines base | -80 |

---

## Dependencies Between Streams

- **Stream A** (Protocol Cleanup) → Independent
- **Stream B** (ABC Simplification) → Independent  
- **Stream C** (Mixin Consolidation) → Independent
- **Stream D** (Generic Registry) → Independent
- **Stream E** (Health & Misc) → Depends on Stream A (lifecycle file changes)

**Recommended parallel execution:** A, B, C, D in parallel, then E, then F.
