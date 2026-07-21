# Phase 0: Emergency P0 — Money Safety

> For agentic workers: Use subagent-driven-development or executing-plans.

**Goal:** Every order path yields correct `OrderResponse.success` and OMS state.

**Architecture:** Fix correctness at transport boundary, OMS lifecycle, and paper gateway. No structural redesign.

## Task 1: Paper success=False on REJECTED

**Files:**
- Modify: `src/brokers/providers/paper/paper_gateway.py:107-112`
- Test: `tests/unit/brokers/paper/test_paper_reject_success.py`

- [ ] Write test asserting `PaperGateway.place_order` returns `success=False` when order status is REJECTED
- [ ] Fix `paper_gateway.py:107`: `success = order.status not in (OrderStatus.REJECTED, ...)`
- [ ] Run test, verify PASS
- [ ] Commit

## Task 2: disclosed_quantity TypeError

**Files:**
- Modify: `src/brokers/providers/dhan/wire.py:117-129`
- Modify: `src/brokers/providers/paper/paper_gateway.py:82-94`
- Modify: `src/domain/ports/order_placement.py:23-37` (signature inspection)
- Test: `tests/unit/brokers/test_disclosed_quantity.py`

- [ ] Write test: `invoke_place_order` with `disclosed_quantity=5` does not raise
- [ ] Add `disclosed_quantity: int = 0` parameter to Dhan `wire.py:place_order` and Paper `paper_gateway.py:place_order`
- [ ] Run test, verify PASS
- [ ] Commit

## Task 3: API async cancel/modify sync bridge

**Files:**
- Modify: `src/interface/api/routers/orders.py:320-324` (cancel)
- Modify: `src/interface/api/routers/orders.py:274-277` (modify)
- Modify: `src/application/oms/_internal/order_lifecycle.py:308-310` (cancel_fn type)
- Test: `tests/unit/interface/api/test_order_cancel_modify.py`

- [ ] Write test: cancel_fn is called and awaited properly
- [ ] In orders.py: make cancel_fn/modify_fn sync by using `asyncio.get_event_loop().run_until_complete` or `run_coro_sync`
- [ ] Or: in order_lifecycle.py: detect coroutine and await it
- [ ] Run test, verify PASS
- [ ] Commit

## Task 4: Idempotency reservation after ambiguous POST

**Files:**
- Modify: `src/brokers/providers/dhan/execution/order_placement.py:97-115`
- Modify: `src/brokers/providers/upstox/orders/order_command_adapter.py:65-82`
- Test: `tests/unit/brokers/test_idempotency_ambiguous.py`

- [ ] Write test: transport exception after POST preserves reservation
- [ ] In order_placement.py: on exception after POST, call `reserve(cid)` not `clear_reservation(cid)`
- [ ] Same for upstox order_command_adapter.py
- [ ] Run test, verify PASS
- [ ] Commit

## Task 5: Upstox CB on 4xx

**Files:**
- Modify: `src/brokers/providers/upstox/auth/http.py:303-317`
- Test: `tests/unit/brokers/upstox/test_cb_4xx.py`

- [ ] Write test: 4xx does not call cb.on_failure
- [ ] In http.py: only call cb.on_failure for transport/5xx errors
- [ ] Run test, verify PASS
- [ ] Commit

## Task 6: Dhan cancel_all_orders error masking

**Files:**
- Modify: `src/brokers/providers/dhan/execution/order_cancellation.py:171-181`
- Test: `tests/unit/brokers/dhan/test_cancel_all_errors.py`

- [ ] Write test: failed cancellation in batch returns False for that item
- [ ] In order_cancellation.py: parse per-order status from response
- [ ] Run test, verify PASS
- [ ] Commit

## Task 7: Token JSON out of source tree

**Files:**
- Modify: `.gitignore`
- Create: `scripts/migrate_tokens.py`
- Test: `tests/unit/brokers/test_token_path.py`

- [ ] Write test: token path resolves to ~/.tradex/tokens/
- [ ] Add `~/.tradex/tokens/` to gitignore
- [ ] Create migration script
- [ ] Run test, verify PASS
- [ ] Commit

## Gate Test

- [ ] All Phase 0 tests pass
- [ ] Existing suite: 0 regressions
- [ ] `progress-tracker.md` updated
