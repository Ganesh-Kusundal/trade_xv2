# ADR-011: Decompose 800+ LOC God Classes

## Status

Proposed

## Context

Several modules in the codebase exceed 800 lines of code, indicating god-class anti-patterns. Large files increase cognitive load, make code review slower, and often indicate mixed responsibilities. Key offenders identified during the architecture audit:

- `application/oms/order_manager.py` — handles order placement, book management, and lifecycle
- `application/streaming/orchestrator.py` — manages subscriptions, data routing, and health
- `interface/ui/services/broker_service.py` — UI broker facade with too many concerns

The existing test `test_deepening_enforcement.py` already checks that `order_manager.py` documents its orchestration contract, but doesn't enforce size limits.

## Decision

Decompose god classes into focused, single-responsibility modules with the following patterns:

### 1. Extract to `_internal/` sub-packages

Following the existing pattern in `application/oms/_internal/`:
- Move implementation details to private sub-modules.
- Keep the public class as a thin facade that delegates to internal components.

### 2. Extract side-effect-free utilities

Functions that compute but don't mutate state should be extracted to standalone modules or moved to `domain/services/`.

### 3. Enforce a 400 LOC soft limit

Files exceeding 400 LOC trigger a review gate. Files exceeding 600 LOC fail CI. This is a **proposed** guardrail (see `guardrails.md`).

### Decomposition targets

| Current File | Proposed Split |
|-------------|---------------|
| `oms/order_manager.py` | `order_manager.py` (facade) + `_internal/book_mutations.py` + `_internal/idempotency.py` |
| `streaming/orchestrator.py` | `orchestrator.py` (facade) + `_internal/subscription_lifecycle.py` + `_internal/data_routing.py` |
| `broker_service.py` | `broker_service.py` (facade) + `_internal/oms_bootstrap.py` + `_internal/cli_facade.py` |

## Consequences

**Positive:**
- Smaller, more focused files are easier to review and test.
- Clear responsibility boundaries reduce merge conflicts.
- Enables targeted testing of extracted components.

**Negative:**
- Initial refactoring effort and risk of regressions.
- More files to navigate (mitigated by clear naming and `__init__.py` re-exports).
- Facade indirection may obscure call chains.

## Enforcement

- `tests/architecture/test_deepening_enforcement.py` — `test_order_manager_documents_orchestration_contract`
- **NEW:** `tests/architecture/test_file_size_limits.py` (proposed — see guardrails.md)
