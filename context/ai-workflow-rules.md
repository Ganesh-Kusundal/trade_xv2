# AI Workflow Rules — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. These are DIRECT COMMANDS to the coding agent,
> not guidelines. This file enforces discipline: stay in scope, verify, and never trade
> real money on an assumption. Read `CLAUDE.md` first; it points here.

## 1. Context First (mandatory gate)

- Before ANY implementation or architectural decision, read the six context files in
  order: `project-overview.md` → `architecture.md` → `code-standards.md` → this file
  → `progress-tracker.md`. (When the Web SPA is implemented, add `web/DESIGN.md`
  after `architecture.md` — it does not exist yet.)
- Before exploring code, run **graphify** (`graphify query/explain/path`) per
  `.cursor/rules/graphify.mdc`. Do not grep/Read blindly.
- If a requirement is ambiguous, resolve against `project-overview.md` and
  `architecture.md`. If still unclear, STOP and ask — do not guess.

## 2. Overall Approach

- Spec-driven, incremental. One unit at a time. No speculative changes.
- Reuse before building: search the codebase (and graphify) for an existing helper,
  util, or pattern before writing new code. No reinvention, no new dependency if an
  installed one covers it.

## 3. Scoping Rules

- Implement exactly the unit/spec. Do NOT add features, refactors, or abstractions not
  required for correctness.
- One unit = one visible, verifiable result, within one system boundary.
- Do not mix UI + DB + background-task changes in a single unit.
- If you find a second bug while fixing one, note it; fix the shared root cause once,
  not per caller. Do not expand scope silently.

## 4. When to Split Work

- Split when a unit touches >1 system boundary or has no single verifiable result.
- Split god-facades (e.g. `UpstoxBroker`) into focused modules per ADR-011.
- Merge tiny adjacent units that always ship together with no standalone result.

## 5. Missing / Ambiguous Requirements

- Do NOT fill gaps with assumptions. Ask the user a specific question.
- If real data is unavailable for a test, halt and request clarification — never fake it.
- For broker/exchange behavior you cannot verify, flag it as an unsafe assumption, not a
  "should work".

## 6. Protected Files (do not modify without explicit instruction)

- `src/domain/` entities/ports — stable core; change only via ADR.
- `docs/architecture/adr/*` — decision records.
- `pyproject.toml` import-linter contracts — adding `ignore_imports` must be justified.
- Generated files: `web/src/api/generated.ts` (planned, not yet generated — the
  Web SPA under `web/` is not implemented; `web/` holds only `.env.example`).
- `src/graphify-out/` — generated artifact (`graphify update src` only; no repo-root graph).

## 7. Documentation & Graph Sync

- Keep `context/*.md` and `docs/architecture/*` in sync with implementation. If a change
  alters architecture/scope/standards, update the relevant file BEFORE continuing.
- After modifying code files under `src/`, run `graphify update src`.
- Update `context/progress-tracker.md` after each meaningful change (see its template).

## 8. Verification Checklist (before declaring done / next unit)

- [ ] Read the six context files + ran graphify orientation for this change.
- [ ] Implemented only the scoped unit; no hidden scope creep.
- [ ] Reused existing code/pattern where one exists.
- [ ] `ruff`, `mypy`, `bandit` clean (per pre-commit).
- [ ] Architecture/import-linter contracts still green.
- [ ] Integration test added/updated verifying real behavior (no mocks).
- [ ] `graphify update src` run; `progress-tracker.md` updated.

## 9. Real-Money Safety (non-negotiable)

- This system trades real money. Any path that can place/cancel an order must be explicit
  about its failure modes; "it should work" is a bug, not a plan.
- Never wire a new execution path without a `RiskGate` and idempotency in place.
- Zero-parity: live code must equal backtest/replay code.
