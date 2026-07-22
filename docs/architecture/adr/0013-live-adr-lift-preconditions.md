# ADR-0013: Live ADR Lift Preconditions

## Status

Proposed — 2026-07-20 (governance gate; **does not lift ADR-0012**)

## Context

ADR-0012 locks product execution to paper-only. Live ADR Readiness Roadmap Phases 0–5
closed code gaps; remaining blockers are operational and governance.

## Preconditions (all required before ADR-0012 amendment)

| # | Gate | Current |
|---|------|---------|
| 1 | Paper PRE-DEPLOY ≥ 7.5 | **8.0** — met |
| 2 | Live PRE-DEPLOY ≥ 8.5 | **6.8** — not met |
| 3 | Weekly chaos + memory green × 4 consecutive weeks on `main` | **0/4** |
| 4 | Live FillSource cancel/modify/capabilities | met |
| 5 | No production fail-open capital paths (ratchet) | met |
| 6 | DP-04 single tick authority | met |
| 7 | Explicit product sign-off on live capital exposure | pending |

## Lift procedure (when gates met)

1. Amend ADR-0012 status to **Superseded** with link here.
2. Enable `ExecutionTargetKind.LIVE` in `runtime/execution_config.py` behind feature flag.
3. Require `validate_production_config(surface="runtime")` + live readiness probe on boot.
4. Update `test_paper_oms_boundary.py` ratchet for new live allowlist.
5. Re-score PRE-DEPLOY live dimensions from rubric (no hand-waved score).

## Explicit non-goals until lift

- No default `TRADEX_EXECUTION_TARGET=live`.
- No silent live submit on operator analytics paths.
- Metrics auth (SEC-004/005) remains separate scope.

## R15 prep (2026-07-22) — seam only, live still blocked

Phase 4 R15 wires the lift **precondition check** without lifting ADR-0012:

- `runtime/execution_config.py`: `assert_live_lift_preconditions()` — double opt-in
  (`TRADEX_ENABLE_LIVE_EXECUTION=1` **and** `TRADEX_ADR_0013_LIFT=1`) plus
  PRE-DEPLOY score ≥ 8.5 and chaos green streak ≥ 4 (env-overridable for CI).
- `validate_production_config(surface="runtime")` invokes the check when
  `TRADEX_EXECUTION_TARGET=live`.
- `runtime/execution_target.py` calls the same check before `BrokerFillSource` wiring.
- Ratchet: `tests/architecture/test_live_lift_prep.py`.

Gates remain **not met** (live PRE-DEPLOY 6.8, chaos 0/4); default target stays PAPER.

## References

- [ADR-0012](0012-paper-only-oms-boundary.md)
- [PRE-DEPLOYMENT-REVIEW-2026-07-20-REVISION.md](../PRE-DEPLOYMENT-REVIEW-2026-07-20-REVISION.md)
