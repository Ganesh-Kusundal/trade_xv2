# MyPy Error Budget

This file tracks the MyPy error count per module. The goal is to *reduce*
this count, not to live with it. Each phase's gate includes a check that
the count has *not increased*.

## Current State (baseline at Phase 0)

Run `mypy brokers/ --show-error-codes 2>&1 | tail -1` to get the total.

### Phase 0 baseline (pre-Phase 0.5)

| Module | Error Count | Last Checked |
|---|---|---|
| `brokers/common/` | TBD | — |
| `brokers/dhan/` | TBD | — |
| `brokers/upstox/` | TBD | — |
| `brokers/paper/` | TBD | — |
| `cli/` | TBD | — |
| **Total** | **411** | 2026-06-12 |

### Phase 0.5 (post-`from __future__ import annotations`)

| Module | Error Count | Last Checked |
|---|---|---|
| `brokers/common/` | — | — |
| `brokers/dhan/` | — | — |
| `brokers/upstox/` | — | — |
| `brokers/paper/` | — | — |
| `cli/` | — | — |
| **Total** | **411** | 2026-06-12 |

**Note:** No mypy error reduction observed. The project targets Python 3.10
where PEP 604 `X | None` syntax is natively supported, so the
`from __future__ import annotations` import does not change type-checker
behaviour on this codebase. The import is still valuable because it:
1. Makes annotations lazy (avoids forward-reference and circular-import
   issues that surface in later phases).
2. Decouples annotation syntax from runtime evaluation, easing future
   moves to Pydantic / dataclass / attrs.
3. Aligns the codebase with the project-wide standard applied during
   Phase 0.5.

## Per-Phase Targets

| Phase | Target | Actual | Delta |
|---|---|---|---|
| Phase 0 | (baseline) | TBD | — |
| Phase 1 | ≤ baseline | TBD | TBD |
| Phase 2 | ≤ baseline - 20% | TBD | TBD |
| Phase 3 | ≤ baseline - 30% | TBD | TBD |
| Phase 4 | ≤ baseline - 40% | TBD | TBD |
| Phase 5 | ≤ baseline - 50% | TBD | TBD |
| Phase 6 | ≤ baseline - 60% | TBD | TBD |
| Phase 7 | ≤ baseline - 70% | TBD | TBD |
| Phase 8 | ≤ baseline - 80% | TBD | TBD |
| Phase 9 | 0 | TBD | TBD |

## How to Run

```bash
# Get total count
mypy brokers/ --show-error-codes 2>&1 | grep -c "error:"

# Get per-module counts
mypy brokers/common/ 2>&1 | grep -c "error:"
mypy brokers/dhan/ 2>&1 | grep -c "error:"
mypy brokers/upstox/ 2>&1 | grep -c "error:"
```

## Strictness Settings

Strict mode will be enabled in Phase 9. Until then, the following
warnings are enabled but non-blocking:

- `disallow_untyped_defs = true`
- `disallow_incomplete_defs = true`
- `warn_unused_ignores = true`
- `warn_redundant_casts = true`
- `warn_return_any = true`

## Known Acceptable Errors

Errors that we explicitly *accept* (with rationale) are listed here:

| Module | Error Code | Count | Rationale |
|---|---|---|---|
| (none yet) | | | |

---

## Status Update — 2026-06-15 (Production Certification Remediation)

The original report above (dated 2026-06-12) described the system BEFORE
the production certification remediation. After 13 commits (A1, A2+A3,
A4, A5, B5, B7, B8+B9, B10, C.1+C.2+C.3, C.4, C.5+C.6, B8+B9 followup,
test_commands polish) the system is in a production-ready state:

- **All 10 blocking issues from PRODUCTION_CERTIFICATION_REPORT resolved.**
- **813 tests passing** (was 805), **0 regressions**, 9 deprecated
  files deleted (~1,800 LOC of dead code).
- **Central OMS on the live CLI path** — every place_order is now
  risk-checked by the canonical RiskManager.
- **HTTP observability surface** — /healthz, /readyz, /metrics live in
  production BrokerService.
- **No leaked daemon threads** — LifecycleManager owns every
  ManagedService, drained on close().

See `docs/PRODUCTION_CERTIFICATION_REPORT.md` for the full remediation
log and the current GO / NO-GO decision.
