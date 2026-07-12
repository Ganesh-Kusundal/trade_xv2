# Engineering Standards

**Version:** 1.0  
**Status:** Phase 3 — Engineering Standards (TRANS-P3-009)  
**Owner:** Integration/Release lane

Canonical testing policy: [TESTING-STRATEGY.md](../reviews/2026-07-11-trading-os-transformation-program/TESTING-STRATEGY.md).  
CI gate semantics: [ADR-019](../architecture/adrs/adr-019-ci-gates.md).

---

## 1. Repository layout

- Single Python root: `src/` with `PYTHONPATH=src` (or editable install).
- Tests mirror layers: `tests/unit`, `tests/component`, `tests/integration`,
  `tests/architecture`, `tests/e2e`.
- No new top-level packages without ADR.

---

## 2. Naming

| Artifact | Convention | Example |
|----------|------------|---------|
| Modules | `snake_case` | `order_lifecycle.py` |
| Classes | `PascalCase` | `PlaceOrderUseCase` |
| Ports | `*Port` suffix | `TracerPort` |
| Events | `SCREAMING_SNAKE` string enum | `ORDER_PLACED` |
| Broker plugins | lowercase id | `dhan`, `upstox`, `paper` |
| Feature flags | `TRADEX_*` | `TRADEX_LEDGER_AUTHORITY` |

---

## 3. Layer imports

Enforced by `lint-imports` and `tests/architecture/`:

- `domain` → nothing outer
- `application` → `domain` only (approved infra debt listed in pyproject.toml)
- `brokers` → `domain`
- `infrastructure` → `domain`
- `interface` → `runtime`, `application` (no broker internals)
- `runtime` / `tradex` → composition only

See [DEPENDENCY_RULES.md](../architecture/DEPENDENCY_RULES.md).

---

## 4. Logging

- Use `application.observability.get_logger(__name__)` in application layer.
- Use stdlib `logging` in domain (no infra).
- Structured fields: `broker_id`, `order_id`, `correlation_id`, `symbol`.
- Never log secrets, tokens, or full auth headers.

---

## 5. Errors

- Domain: raise typed exceptions from `domain.errors` (no broker codes).
- Application: map to result types at boundaries; fail closed on UNKNOWN.
- Interface: format via `error_formatter`; never leak stack traces to CLI JSON.

**Invariant:** `UNKNOWN` order status never auto-retries without reconciliation.

---

## 6. Observability

- Application code uses `application.observability.trace_operation` (no-op default).
- Real OTEL wiring lives in composition roots (`runtime`, `infrastructure`).
- Audit emissions (`emit_*`) remain approved debt until AuditPort exists.

---

## 7. Broker plugins

1. Register via `pyproject.toml` entry point `tradex.brokers`.
2. Call `register_segment_mapper(broker_id, factory)` in `brokers.<id>.__init__`.
3. Implement `SegmentMapper` + wire adapter; no edits to `domain/` for new broker.
4. Pass `broker verify` / `broker certify` before production enablement.

---

## 8. CI (local parity)

```bash
PYTHONPATH=src lint-imports --config pyproject.toml
PYTHONPATH=src ruff check src tests
PYTHONPATH=src pytest tests/unit tests/component tests/architecture -q
PYTHONPATH=src pytest tests/architecture/test_workflow_paths.py -q
```

PRs must pass blocking gates per ADR-019.

---

## 9. Documentation

- Behavior change → update flow doc or ADR.
- New event → append to `EVENT_CATALOG.md` (never insert mid-list).
- Deprecations: `DeprecationWarning` + removal task in backlog.

---

## 10. PR checklist

- [ ] Layer imports respected
- [ ] Architecture tests added/updated for new boundaries
- [ ] No `continue-on-error` on blocking steps
- [ ] Feature flag default safe (off for capital-moving paths)
- [ ] Evidence command output in PR description for integration changes