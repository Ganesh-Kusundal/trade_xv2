# Coverage History

Per-phase coverage deltas. We track *branch coverage* on critical paths,
not just line coverage.

## Aggregate

| Phase | Line % | Branch % | Delta |
|---|---|---|---|
| Phase 0 (baseline) | TBD | TBD | — |
| Phase 1 | TBD | TBD | TBD |
| Phase 2 | TBD | TBD | TBD |
| Phase 3 | TBD | TBD | TBD |
| Phase 4 | TBD | TBD | TBD |
| Phase 5 | TBD | TBD | TBD |
| Phase 6 | TBD | TBD | TBD |
| Phase 7 | TBD | TBD | TBD |
| Phase 8 | TBD | TBD | TBD |
| Phase 9 | TBD | TBD | TBD |

## Per-Module (Phase 0 baseline)

To be populated by the Build Engineer.

## How to Run

```bash
pytest --cov=brokers --cov-branch --cov-report=term-missing --cov-report=html
```

The HTML report is at `htmlcov/index.html`.

## Critical Paths (must be ≥90% branch coverage)

- `brokers/common/core/auth.py` — token lifecycle
- `brokers/common/resilience/` — circuit breaker, retry, rate limiter
- `brokers/dhan/orders/order_command_adapter.py` — order placement/cancellation
- `brokers/dhan/instrument_service.py` — symbol resolution
- `brokers/gateway.py` — public API

## Exclusions

Lines excluded from coverage measurement (with rationale):

| File | Pattern | Rationale |
|---|---|---|
| (none yet) | | |