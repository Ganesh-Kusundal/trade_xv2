# Trade_XV2 — Reviews & Planning Index

**Purpose:** single source-of-truth index for all architecture reviews and the transformation program on branch `refactor/structural-cleanup`.
**Rule:** docs are inputs, not truth. Verify claims against the working tree before acting.

## Artifact roles

| Artifact | Role | Currency |
|----------|------|----------|
| [`2026-07-11-trading-os-transformation-program/`](./2026-07-11-trading-os-transformation-program/README.md) | **Program-of-record** — phases, `TRANS-*` backlog, team ownership, risk register, execution plan | Active (Iteration 1 logged in `PHASE-STATUS.md`) |
| [`2026-07-11-trading-os-architecture-audit/`](./2026-07-11-trading-os-architecture-audit/README.md) | **Phase 0 evidence snapshot** — repository/flow/architecture/validation audits, A/B/C backlog (`AUDIT-*`) | Reconciled 2026-07-11 (verdict table updated to verified state) |
| [`2026-07-10-trading-platform-review/`](./2026-07-10-trading-platform-review/README.md) | **Historical prior review** — 11 reports; hypotheses confirmed by the 07-11 audit | Superseded by 07-11 audit for current state |
| `../../.kilo/plans/1783693185737-brokers-architectural-audit.md` | **Phase 5 engineering detail** — broker-kernel strangler (`REF-0`…`REF-9`) | Active; fold `REF-*` into `TRANS-*` backlog (see open items) |

## How to read

1. **Plan & execution status** → transformation-program (`PHASE-STATUS.md`).
2. **Evidence & findings** → architecture-audit (verdict table is a verified snapshot; rows originally marked "Broken" were at audit-start and are reconciled).
3. **Concrete broker refactor work** → kilo plan `REF-*` tasks; these are the Phase 5 engine and should be tracked as `TRANS-*` items to avoid duplicate trackers.

## Open reconciliation items

- [ ] Fold `.kilo` broker `REF-*` IDs into `TRANS-*` backlog (single tracker for Phase 5).
- [ ] Wire `tests/architecture/test_workflow_paths.py` into CI (AUDIT-001 acceptance not yet enforced).
- [ ] Close `continue-on-error` safety gates (AUDIT-006): `ci.yml:189,391,395,424`, `mutation_testing.yml:30`.
- [ ] Author Phase 2 flow state machines (`FLOWS.md` / `STATE_MACHINES.md`) from audit traces.
