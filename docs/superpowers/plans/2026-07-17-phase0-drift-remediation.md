# Phase 0 Drift Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the 15 architectural drifts (D1–D15) discovered in the Phase 0 audit of TradeXV2, safety-first, with redesign where the auditor flagged the gate as unsafe.

**Architecture:** Five independent subsystem plans executed in priority order. **P1 (real-money safety) must complete and be verified before any structural work in P2–P5 begins** — the system must not gain complexity while a live-account order gate is bypassable. Each subsystem plan produces independently testable, committable software. "Redesign where required" means: the live-order gate is lifted to a single composition-root-enforced authority (not a per-leaf patch), and import-linter is made fail-closed (not warn-only).

**Tech Stack:** Python 3.13 (toolchain), `requires-python>=3.10` (runtime floor), FastAPI, Pydantic v2, pytest + pytest-asyncio, import-linter (`lint-imports`), PYTHONPATH=src.

## Global Constraints

- Run all tests with: `PYTHONPATH=src python -m pytest <path> -q`
- Run import-linter per contract with: `PYTHONPATH=$(pwd)/src lint-imports --config pyproject.toml`
- This system **trades real money**. Every order-placing path must pass an explicit `RiskGate` + `allow_live_orders` check before reaching any broker executor. "It should work" is a bug.
- **Zero-parity rule:** backtest, replay, and live execution share identical OMS logic. No divergent fill path may be introduced.
- Never add `skip_parity_gate=True` from code — only the `SKIP_PARITY_GATE` env var may disable it, and never in prod (see P1-T4).
- Do NOT modify `domain` entity logic, `domain.ports` Protocols, or broker wire adapters unless they are the direct cause of a failing test. Changes to the gate belong in `application`/`infrastructure`/`runtime`, wired at the composition root.
- Commit after every task; message format: `fix(<scope>): <description>`.
- Do not delete production code that has live importers; verify with grep first.
- Trust the audit's file:line citations; re-verify any line number that looks off before editing (files shift between sessions).

---

# PLAN P1 — Real-Money Safety (D2 / D3 / D4)

Highest priority. Closes the unguarded live super/forever/exit-all path, makes `require_live_broker` enforce the gate, and makes the parity gate non-bypassable in production.

## P1 File Structure

- Create: `src/application/oms/live_order_authority.py` — single composition-root-enforced authority combining `check_live_actionable` + `allow_live_orders` flag + kill-switch + risk. Called by ALL order paths.
- Modify: `src/brokers/services/_session.py:43` (`check_live_actionable`) — keep as the live-actionable half; authority wraps it.
- Modify: `src/brokers/dhan/execution/super_orders.py:40`, `forever_orders.py:40`, `exit_all.py:20` — call the authority before the wire `post`.
- Modify: `src/brokers/upstox/orders/exit_all_adapter.py:30` and the Upstox super/forever adapters — same.
- Modify: `src/application/oms/extended_order_service.py:106-110` — `_check_risk` must **reject** on coercion failure, not return `None`.
- Modify: `src/interface/api/deps.py:256-272` (`require_live_broker`) — enforce the authority.
- Modify: `src/interface/ui/commands/extended_orders.py` — route through the authority (not `gw._broker.*` directly).
- Modify: `src/runtime/parity_gate.py:16-32` — forbid `SKIP_PARITY_GATE` in live envs at the gate itself.
- Modify: `src/runtime/resilience.py:75` — `parity_gate_enabled` must be forced `True` when `TRADEX_ENV` in {production, staging}.
- Test: `tests/unit/application/oms/test_live_order_authority.py`
- Test: `tests/unit/brokers/dhan/test_extended_order_gate.py`
- Test: `tests/unit/interface/api/test_require_live_broker.py`
- Test: `tests/architecture/test_parity_gate_unbypassable.py`

## P1-T1: Live Order Authority (the single gate)

**Files:** Create `src/application/oms/live_order_authority.py`; Test `tests/unit/application/oms/test_live_order_authority.py`

**Interfaces:**
- Consumes: `brokers.services._session.check_live_actionable(broker: str)`, `domain.ports.risk_manager.RiskManagerPort`, a boolean `allow_live_orders` resolved from the active broker profile (`config/profiles/base.py:154 allow_live_orders_by_default`).
- Produces: `def authorize_live_order(*, broker: str, allow_live_orders: bool, risk_manager: Any, live_actionable: Callable[[], bool] | None = None, risk_payload: dict[str, Any] | None = None) -> None` — raises `LiveBrokerBlockedError` / `RiskRejectedError` on any failure; returns `None` only when the order may proceed.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/application/oms/test_live_order_authority.py
import pytest
from brokers.services._session import LiveBrokerBlockedError
from application.oms.live_order_authority import authorize_live_order, RiskRejectedError


def test_paper_broker_always_allowed():
    authorize_live_order(broker="paper", allow_live_orders=False, risk_manager=None)


def test_live_blocked_when_flag_off():
    with pytest.raises(LiveBrokerBlockedError):
        authorize_live_order(
            broker="dhan", allow_live_orders=False,
            risk_manager=None, live_actionable=lambda: True,
        )


def test_live_blocked_when_gate_unset():
    with pytest.raises(LiveBrokerBlockedError):
        authorize_live_order(
            broker="dhan", allow_live_orders=True,
            risk_manager=None, live_actionable=None,
        )


def test_risk_rejects_malformed_payload():
    # coercion failure must REJECT, not skip (fixes D2 _check_risk bug)
    class RM:
        def is_kill_switch_active(self): return False
        def check_order(self, order): raise AssertionError("should not be called")
    with pytest.raises(RiskRejectedError):
        authorize_live_order(
            broker="dhan", allow_live_orders=True,
            risk_manager=RM(), live_actionable=lambda: True,
            risk_payload={"symbol": "RELIANCE"},  # missing side/quantity -> unbuildable
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/unit/application/oms/test_live_order_authority.py -q`
Expected: FAIL — `ModuleNotFoundError: application.oms.live_order_authority`

- [ ] **Step 3: Write minimal implementation**

```python
# src/application/oms/live_order_authority.py
from __future__ import annotations
import logging
from typing import Any, Callable

from brokers.services._session import check_live_actionable, LiveBrokerBlockedError
from domain.exceptions import TradeXV2Error

logger = logging.getLogger(__name__)


class RiskRejectedError(TradeXV2Error):
    """Raised when an order fails the pre-trade risk path (incl. unbuildable payload)."""


def authorize_live_order(
    *,
    broker: str,
    allow_live_orders: bool,
    risk_manager: Any | None,
    live_actionable: Callable[[], bool] | None = None,
    risk_payload: dict[str, Any] | None = None,
) -> None:
    """Single live-order authority. ALL order paths must call this first.

    Order of checks (fail-closed at every step):
      1. live-actionable gate (composition-root registered) — blocks if unset/False.
      2. allow_live_orders flag — the env/profile switch; False => blocked for live.
      3. kill-switch (via risk_manager).
      4. full risk path — an unbuildable payload is a REJECTION, never a silent pass.
    """
    check_live_actionable(broker)  # raises LiveBrokerBlockedError if not actionable
    if broker.lower() in {"dhan", "upstox"} and not allow_live_orders:
        raise LiveBrokerBlockedError(
            f"OMS refused: allow_live_orders is disabled for broker '{broker}'."
        )
    if risk_manager is None:
        return
    if getattr(risk_manager, "is_kill_switch_active", lambda: False)():
        raise RiskRejectedError("Kill switch active — order rejected")
    if risk_payload is None:
        return
    from decimal import Decimal
    from domain import Order, OrderStatus, OrderType, ProductType, Side, Validity
    try:
        order = Order(
            order_id="", symbol=risk_payload.get("symbol", ""),
            exchange=risk_payload.get("exchange", "NSE"),
            side=Side(risk_payload.get("side", "BUY")),
            order_type=OrderType(risk_payload.get("order_type", "MARKET")),
            quantity=int(risk_payload.get("quantity", 0)),
            price=Decimal(str(risk_payload.get("price", "0"))),
            product_type=ProductType(risk_payload.get("product_type", "INTRADAY")),
            status=OrderStatus.OPEN, validity=Validity(risk_payload.get("validity", "DAY")),
        )
    except (ValueError, TypeError) as exc:
        # ponytail: ceiling = malformed payload could slip past risk if we returned
        # None here; we instead hard-reject because an order we cannot model is an
        # order we cannot risk-check. Upgrade path = schema-validate payload upstream.
        raise RiskRejectedError(f"Order payload could not be risk-modelled: {exc}") from exc
    result = risk_manager.check_order(order)
    if not result.allowed:
        raise RiskRejectedError(result.reason or "Risk check rejected order")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/unit/application/oms/test_live_order_authority.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/application/oms/live_order_authority.py tests/unit/application/oms/test_live_order_authority.py
git commit -m "fix(safety): add single live-order authority gate (D2)"
```

## P1-T2: Extended-order executors call the authority

**Files:** Modify `src/brokers/dhan/execution/super_orders.py`, `forever_orders.py`, `exit_all.py`; Test `tests/unit/brokers/dhan/test_extended_order_gate.py`

**Interfaces:** Consumes `application.oms.live_order_authority.authorize_live_order`. Produces: executors raise `LiveBrokerBlockedError`/`RiskRejectedError` before any `self._client.post`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/brokers/dhan/test_extended_order_gate.py
import pytest
from unittest.mock import MagicMock
from brokers.services._session import LiveBrokerBlockedError


def test_super_order_blocked_when_flag_off():
    from brokers.dhan.execution.super_orders import SuperOrdersAdapter
    adapter = SuperOrdersAdapter.__new__(SuperOrdersAdapter)
    adapter._client = MagicMock()
    adapter._broker_id = "dhan"
    with pytest.raises(LiveBrokerBlockedError):
        adapter.place_super_order(
            symbol="RELIANCE", qty=1,
            authorize=lambda **k: (_ for _ in ()).throw(LiveBrokerBlockedError("blocked")),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/unit/brokers/dhan/test_extended_order_gate.py -q`
Expected: FAIL (adapter currently posts without authorizing)

- [ ] **Step 3: Add an `authorize` callable param to each executor's public method**

In `super_orders.py`, `forever_orders.py`, `exit_all.py`, change the public method signature to accept `authorize: Callable[..., None] | None = None` and call it as the **first** line, before `self._client.post`:

```python
def place_super_order(self, symbol, qty, *, authorize=None, **kw):
    if authorize is not None:
        authorize(broker=self._broker_id, risk_payload={"symbol": symbol, "side": "BUY"})
    # ... existing self._client.post("/supers/...) below unchanged
```

Apply the same pattern to `forever_orders.py:40` and `exit_all.py:20` (exit_all is the highest-risk — flattening all positions — so `authorize` is mandatory there).

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/unit/brokers/dhan/test_extended_order_gate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/brokers/dhan/execution/super_orders.py src/brokers/dhan/execution/forever_orders.py src/brokers/dhan/execution/exit_all.py tests/unit/brokers/dhan/test_extended_order_gate.py
git commit -m "fix(safety): gate dhan super/forever/exit-all behind live-order authority (D2)"
```

## P1-T3: `require_live_broker` enforces the gate

**Files:** Modify `src/interface/api/deps.py:256-272`; Test `tests/unit/interface/api/test_require_live_broker.py`

**Interfaces:** Consumes `application.oms.live_order_authority.authorize_live_order`. Produces: dependency raises 503/403 when not live-actionable or flag off.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/interface/api/test_require_live_broker.py
import pytest
from unittest.mock import MagicMock
from types import SimpleNamespace
from interface.api import deps


def test_require_live_broker_blocks_when_flag_off(monkeypatch):
    svc = MagicMock(); svc.active_broker = "dhan"
    monkeypatch.setattr(deps, "_container", SimpleNamespace(broker_service=svc))
    monkeypatch.setattr(deps, "authorize_live_order",
                        lambda **k: (_ for _ in ()).throw(deps.LiveBrokerBlockedError("no")))
    with pytest.raises(deps.HTTPException):
        deps.require_live_broker()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/unit/interface/api/test_require_live_broker.py -q`
Expected: FAIL (current `require_live_broker` ignores the gate)

- [ ] **Step 3: Edit `require_live_broker` to call the authority**

```python
def require_live_broker():
    svc = _resolve_broker_service()  # existing resolution
    if svc is None:
        raise HTTPException(status_code=503, detail="Broker service unavailable")
    broker = svc.active_broker_name or "dhan"
    try:
        authorize_live_order(
            broker=broker,
            allow_live_orders=getattr(svc, "allow_live_orders", False),
            risk_manager=getattr(svc, "risk_manager", None),
            live_actionable=_LiveGateState.gate,
        )
    except LiveBrokerBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RiskRejectedError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return svc.active_broker
```

(Import `authorize_live_order`, `LiveBrokerBlockedError`, `RiskRejectedError` at top of `deps.py`; ensure `HTTPException` already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/unit/interface/api/test_require_live_broker.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/interface/api/deps.py tests/unit/interface/api/test_require_live_broker.py
git commit -m "fix(safety): require_live_broker enforces live-order authority (D3)"
```

## P1-T4: Parity gate unbypassable in prod

**Files:** Modify `src/runtime/parity_gate.py:16-32`, `src/runtime/resilience.py:75`; Test `tests/architecture/test_parity_gate_unbypassable.py`

**Interfaces:** Consumes `os.getenv("TRADEX_ENV")`. Produces: gate always runs in prod/staging regardless of `SKIP_PARITY_GATE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/architecture/test_parity_gate_unbypassable.py
import os
import types
from unittest.mock import MagicMock
from runtime import parity_gate


def test_skip_env_ignored_in_production(monkeypatch):
    monkeypatch.setenv("TRADEX_ENV", "production")
    monkeypatch.setenv("SKIP_PARITY_GATE", "1")
    called = {}
    fake = MagicMock(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(parity_gate.subprocess, "run",
                        lambda *a, **k: called.setdefault("ran", True) or fake)
    parity_gate.assert_runtime_parity_or_raise()
    assert called.get("ran") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/architecture/test_parity_gate_unbypassable.py -q`
Expected: FAIL (current code early-returns on `SKIP_PARITY_GATE=1` even in prod)

- [ ] **Step 3: Edit `parity_gate.py` so live envs ignore the skip flag**

```python
def assert_runtime_parity_or_raise():
    env = (os.getenv("TRADEX_ENV") or "development").strip().lower()
    is_live_env = env in ("production", "staging")
    if not is_live_env and os.getenv("SKIP_PARITY_GATE", "0") == "1":
        logger.debug("parity_gate: skipped (SKIP_PARITY_GATE=1, env=%s)", env)
        return
    if not is_live_env and os.getenv("PYTEST_CURRENT_TEST"):
        return
    # --- live envs ALWAYS run below; SKIP_PARITY_GATE is ignored ---
    ...  # existing verifier block unchanged
```

And in `resilience.py:75`, force the flag in live envs:

```python
parity_gate_enabled = (
    os.getenv("SKIP_PARITY_GATE", "0") != "1"
    or os.getenv("TRADEX_ENV", "").strip().lower() in ("production", "staging")
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src python -m pytest tests/architecture/test_parity_gate_unbypassable.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/parity_gate.py src/runtime/resilience.py tests/architecture/test_parity_gate_unbypassable.py
git commit -m "fix(safety): parity gate cannot be skipped in prod/staging (D4)"
```

**P1 Exit Gate:** All P1 tests pass AND `PYTHONPATH=src python -m pytest tests/unit/brokers/dhan/test_extended_order_gate.py tests/unit/interface/api/test_require_live_broker.py tests/architecture/test_parity_gate_unbypassable.py -q` green. Only then proceed to P2.

---

# PLAN P2 — Layering & Contract Correctness (D5 / D6 / D9 / D11)

Make import-linter fail-closed and fix the four confirmed violations.

## P2 File Structure

- Modify: `pyproject.toml` — for the violated contracts, change `unmatched_ignore_imports_alerting = "warn"` to the behavior that fails CI (preferred: fix the violations, then keep `warn`; if a contract cannot be fixed this pass, set `"error"`).
- Modify: `src/application/oms/context/lifecycle.py:16` — stop subclassing `infrastructure.lifecycle.lifecycle.ManagedService`; implement `ManagedServicePort` from `domain.ports.lifecycle` instead.
- Modify: `src/application/trading/multi_strategy_runtime.py:18-19`, `src/application/trading/feature_fetcher.py:12` — inject `StrategyPipeline`/`FeaturePipeline` via `runtime` composition, not direct `analytics` import.
- Modify: `src/interface/ui/services/connect.py:13`, `broker_registry.py:13` — use `runtime.broker_accessors` instead of `infrastructure.gateway.factory`.
- Modify: `src/brokers/dhan/config/settings.py:33`, `order_placement.py:25`, `upstox/auth/urls.py:22` — receive endpoints via constructor injection from the composition root instead of `from config.endpoints import ...`.
- Test: `tests/architecture/test_application_no_infra_imports.py` (exists — extend to assert violations gone), `tests/architecture/test_ui_no_concrete_broker_imports.py` (exists).

## P2-T1: Make import-linter fail-closed for the violated contracts

- [ ] **Step 1: Run lint-imports to capture current violations**

Run: `PYTHONPATH=$(pwd)/src lint-imports --config pyproject.toml 2>&1 | tail -30`
Expected: warnings listing `application -> infrastructure`, `application -> analytics`, `interface.ui -> infrastructure.gateway.factory`.

- [ ] **Step 2: Change alerting to error for those three contracts** in `pyproject.toml` (set `unmatched_ignore_imports_alerting = "error"` on the "Application infrastructure separation", "Analytics does not import Trading OMS/execution (D2 inverse)", and "UI uses connect shims" contracts). Keep `warn` only where a documented deferred item remains.

- [ ] **Step 3: Commit the tightened contract**

```bash
git add pyproject.toml
git commit -m "fix(layering): make violated import-linter contracts fail-closed (D5)"
```

## P2-T2: Stop `application` subclassing `infrastructure`

- [ ] **Step 1: Write a test asserting `TradingContextLifecycleMixin` does not import `infrastructure.lifecycle.lifecycle`**

```python
# in tests/architecture/test_application_no_infra_imports.py
def test_lifecycle_mixin_avoids_infra_base():
    import inspect
    from application.oms.context import lifecycle
    src = inspect.getsource(lifecycle)
    assert "infrastructure.lifecycle.lifecycle" not in src
```

- [ ] **Step 2: Edit `lifecycle.py:16`** — remove `from infrastructure.lifecycle.lifecycle import ManagedService` and the base-class inheritance; instead depend on `ManagedServicePort` from `domain.ports.lifecycle` (exists at `domain/ports/lifecycle.py:24`). Implement the port methods directly.

- [ ] **Step 3: Run the test + lint-imports** → PASS, no `application -> infrastructure` warning. Commit.

## P2-T3: Break `application -> analytics` and `interface.ui -> gateway.factory`

- [ ] **Step 1: Replace direct `analytics` imports in `multi_strategy_runtime.py`/`feature_fetcher.py` with injection of pre-built `StrategyPipeline`/`FeaturePipeline` from the composition root (`runtime/factory.py` already constructs them locally — pass them in).**
- [ ] **Step 2: Replace `connect.py:13`/`broker_registry.py:13` `infrastructure.gateway.factory` imports with `runtime.broker_accessors` (the accessor abstraction the contract intends).**
- [ ] **Step 3: Run `lint-imports` → clean. Add regression asserts. Commit `fix(layering): remove application->analytics and ui->gateway.factory (D6/D9)`.**

## P2-T4: Inject broker config instead of `from config.endpoints`

- [ ] **Step 1: Change `settings.py`/`order_placement.py`/`urls.py` to accept endpoint constants via `__init__` params set by the composition root, removing the top-level `from config.endpoints import ...`.**
- [ ] **Step 2: Grep confirm no `brokers/**` file imports `config.endpoints`/`config.ws_settings` directly. Commit `fix(layering): inject broker endpoints via composition root (D11)`.**

**P2 Exit Gate:** `PYTHONPATH=$(pwd)/src lint-imports --config pyproject.toml` exits 0 (no errors).

---

# PLAN P3 — Zero-Parity Hazards (D7 / D12)

Collapse divergent trade/position shapes and consolidate event-bus implementations.

## P3 File Structure

- Modify: `src/analytics/shared/trade_types.py` — make `SimTrade`/`SimPosition` the single shape; have `replay/models.py` + `paper/models.py` re-export/adapt from it (they already carry `ponytail:` notes saying "domain Trade is SSOT" — align them to `SimTrade`/`SimPosition`).
- Modify: `src/analytics/replay/models.py:204,246`, `src/analytics/paper/models.py:129,196` — delegate to `shared.trade_types`.
- Modify: `src/infrastructure/event_bus/` — keep `EventBus` (sync) as canonical; `AsyncEventBus` is already a thin wrapper; document `NullEventBus` as test-only; clarify `EventBusService` (UI) is a facade, not a bus.
- Test: `tests/unit/analytics/test_shared_trade_types.py` (extend to assert replay+paper use the shared shape).

## P3-T1: Wire `shared/trade_types.py` into replay + paper

- [ ] **Step 1: Write a test asserting `SimulatedTrade`/`PaperTrade` are `SimTrade`/`SimPosition` (or narrow adapters over them).**
- [ ] **Step 2: Refactor `replay/models.py` + `paper/models.py` to subclass/adapt `SimTrade`/`SimPosition` from `shared.trade_types`; delete the duplicated field definitions.**
- [ ] **Step 3: Run the analytics replay/paper suites + parity tests. Commit `fix(zeroparity): unify trade/position shapes via shared/trade_types (D7)`.**

## P3-T2: Event-bus consolidation clarity

- [ ] **Step 1: Add `tests/architecture/test_single_bus.py` assertion that only one concrete `EventBus` subclass implements `EventBusPort` in production code (exclude `NullEventBus` + UI facade).**
- [ ] **Step 2: Document `NullEventBus`/`EventBusService` roles; no deletion (avoid scope creep). Commit `fix(zeroparity): document event-bus single-impl boundary (D12)`.**

**P3 Exit Gate:** No duplicate trade/position field definitions remain; single-bus test passes.

---

# PLAN P4 — Documentation Truth (D1 / D10)

Make docs match reality: the Web SPA does not exist; the "API→UI inversion" finding is stale.

## P4 File Structure

- Modify: `context/project-overview.md`, `context/architecture.md`, `docs/architecture/*` — remove/flag the Web SPA claims; mark `web/` as not-yet-built.
- Modify: `context/progress-tracker.md` — strike the "API→UI inversion" finding (verified absent in source).
- Test: none (doc-only). Gate = `grep` that `web/src/api/generated.ts` is no longer referenced.

## P4-T1: Correct the Web SPA claims

- [ ] **Step 1: Grep repo for `web/src/api/generated.ts` and `web/` SPA references in docs.**
- [ ] **Step 2: Edit the docs to state the SPA is not present in this revision (only `web/.env.example` exists) and remove claims that `generated.ts` is regenerated. Commit `docs: correct Web SPA claims — SPA not present (D1)`.**

## P4-T2: Strike stale "API→UI inversion" finding

- [ ] **Step 1: Edit `progress-tracker.md` to mark the finding resolved/verified-absent. Commit `docs: strike stale API->UI inversion finding (D10)`.**

**P4 Exit Gate:** No doc asserts an existing Web SPA; finding list is accurate.

---

# PLAN P5 — Test Integrity (D13)

Reconcile the "no mocks / integration tests only" rule with the 1620 MagicMock refs.

## P5 File Structure

- Modify: `context/code-standards.md` + policy docs — replace the absolute "no mocks" claim with the accurate policy: fakes are permitted for protocol seams (OMS/broker ports) but live paths (parity, real-money gate) must be validated against real components.
- Add: `tests/architecture/test_no_mock_in_integration.py` — assert `tests/integration/**` and `tests/component/**` do not use `MagicMock`/`mock.patch` for the order/gate/parity path.
- Test: the new architecture test.

## P5-T1: Constrain mocks on the safety-critical path

- [ ] **Step 1: Write `tests/architecture/test_no_mock_in_integration.py`** that fails if `tests/integration/**/{test_*order*,test_*gate*,test_*parity*}.py` contain `MagicMock`/`mock.patch`.
- [ ] **Step 2: Audit those specific files; replace mock-based order/gate tests with real-component or `tests/fakes` protocol fakes (already exists: `tests/fakes/fake_oms.py`).
- [ ] **Step 3: Update `code-standards.md` to state the real policy. Commit `fix(tests): ban mocks on safety-critical integration paths; correct policy (D13)`.**

**P5 Exit Gate:** New architecture test passes; safety-critical integration tests use real components or protocol fakes, not `MagicMock`.

---

## Execution Order & Handoff

1. **P1** (real-money safety) — must finish and verify before any other plan.
2. **P2** (layering) — can start after P1.
3. **P3, P4, P5** — independent of each other; sequence P3 (parity) then P4 (docs) then P5 (tests), or parallelize.

Each subsystem plan above is independently committable. Do **not** begin P2–P5 structural changes while P1 is incomplete.

Plan complete and saved to `docs/superpowers/plans/2026-07-17-phase0-drift-remediation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for P1 where safety review between tasks matters.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
