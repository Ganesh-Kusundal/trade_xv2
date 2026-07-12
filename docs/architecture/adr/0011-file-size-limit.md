# ADR-0011: Enforce a file-size limit (400 soft / 650 hard)

- **Status:** Accepted
- **Date:** 2026-07-12
- **Deciders:** Architecture review
- **Companion:** `tests/architecture/test_file_size_limit.py`

## Context
God-class modules (800+ LOC) had repeatedly appeared: `RiskManager` (678), `TradingContext`
(809), `UpstoxTokenManager` (574), `PaperTradingEngine` (562), `Analytics` facade (549),
`HistoricalDataCoordinator` (567), `services/core.py` (570), `DhanExtendedCapabilities`
(366), plus `session.py` (512). Each slowed review, raised cognitive load, and hid
responsibilities. Without an automated ceiling the decomposition work silently regresses
(large files keep appearing, e.g. a new 905-LOC `capability_manifest/catalog.py`).

## Decision
Enforce a maximum file size via an **architecture test** (not just a lint flag):

- **SOFT limit = 400 LOC** — any `src/**/*.py` over this must carry an approved exemption.
- **HARD limit = 650 LOC** — any file over this *without* an exemption fails CI.
- LOC = non-blank, non-comment lines (`_count_lines` in the test).
- Exemptions are an **explicit allowlist** in `test_file_size_limit.py`
  (`EXEMPTIONS` dict: `relative_path → (approved_limit, reason)`). Each entry must point
  to a real file within 10% of its approved limit (`test_exemptions_are_accurate`), so
  stale exemptions fail.
- New exemptions require an owner + a Phase-5 decomposition task in the backlog; the list
  is driven to **zero** over Phase 5 (GG-2 / P5-10).

The gate runs in CI via `@pytest.mark.architecture` (the `architecture-enforcement`
workflow), so it is a real merge blocker, not advisory.

## Consequences
- Positive: a hard ceiling prevents future god classes; the allowlist makes current debt
  explicit and auditable; `test_exemptions_are_accurate` stops the list going stale.
- Negative: 38 files currently exceed the limits and are exempted — several far above 650
  (`capability_manifest/catalog.py` 895, `domain/universe.py` 700, `candles/historical.py`
  666, `analytics/precompute_features.py` 678). These are tracked debt, not free passes.
- Cost: each exempted file must eventually be decomposed (P5-10) and its exemption removed.

## Validation
- `pytest tests/architecture/test_file_size_limit.py` is green on the current tree.
- Adding a file >400 LOC without an exemption fails `test_no_file_exceeds_soft_limit_without_exemption`.
- A file >650 LOC without an exemption fails `test_no_file_exceeds_hard_limit`.
- Removing/changing an exempted file incorrectly fails `test_exemptions_are_accurate`.

## Status
- **Accepted and implemented** (10+ commits reference "per ADR-011", e.g. `b6f83096`,
  `82e2080c`, `3e4d8c64`). This ADR document was written retroactively to record the
  decision those commits referenced, and to correct the earlier review claim that the
  limit was "not enforced" — it is enforced, but was initially neutered by a large
  exemption list that GG-2 / P5-10 now retire.
