# Review Challenge — Independent Domain Purity Slice

**Date:** 2026-07-09  
**Against:** `reports/ARCHITECTURE_REVIEW_BOARD_2026-07-09.md`  
**Status:** Verified + applied (this document records overturned board claims)

## Verdict matrix

| Board claim | Independent finding | Action taken |
|-------------|---------------------|--------------|
| **X2** `domain → plugins` is P0 (4 violations) | **False (current tree).** Zero prod imports. Direction is `plugins → domain`. | **Reject X2 “fix”.** No code change needed for inversion. |
| **X9** delete `domain.aggregates` after zero-ref | **False.** Live imports from `domain/__init__`, factories, accounts/positions re-exports, analytics. | **Do not delete.** Keep aggregates package; `InstrumentAggregate` remains alias of canonical `Instrument`. |
| Domain isolation is “clean” | **Guards were lying.** Isolation test scanned `ROOT/domain` (missing → 0 files → silent pass). | **A1 fixed:** scan `src/domain` + non-empty assert. |
| import-linter always checks this domain | **Risk real**, machine-dependent. On this workspace `domain` resolves here when `src` is on path; bare envs can shadow via other `.pth` installs. | **A2:** CI `PYTHONPATH` pin + `domain.__file__` in-repo guard; document pin in `pyproject.toml`. |
| **X7** pandas in domain core | **Confirmed.** Top-level imports in indicators, instrument, services, market_data port. | **A3 applied:** pure series indicators; `Instrument.history` → `HistoricalSeries`; lazy pandas only at export. |

## Agreements with the board (unchanged)

- Hexagonal ports, Instrument as primary object, `tradex.Session` composition root, OMS in `application/oms`, broker self-registration: keep.
- “Users touch market objects, not brokers” remains the product north star.
- Waves B/C/E (kernel, OMS spine, datalake↔analytics) remain larger separate slices — already partially landed on this branch; this challenge only re-bases **domain purity**.

## A4 aggregates decision (refined)

Canonical **behavior** lives in `domain.instruments.instrument.Instrument`.  
`domain.aggregates.instrument.InstrumentAggregate` is a **deprecated alias** (emits `DeprecationWarning`) — keep for analytics/factory importers until a dedicated migration.  
Deleted stray `instrument.py.old`.

Do **not** promote aggregates as the only spine until analytics migrates off `InstrumentAggregate` imports.

## Checks left behind

1. `tests/architecture/test_domain_isolation.py` — real `src/domain` scan + non-empty + plugins forbidden + in-repo resolve.
2. `tests/architecture/test_domain_no_pandas_import.py` — core domain modules import with `pandas` blocked.
3. CI: `PYTHONPATH=…/src:…` for `lint-imports` + resolve assertion.

## Explicit non-goals of this slice

- Not re-doing Wave B/C OMS/kernel work.
- Not renaming package `domain` → namespaced package.
- Not deleting other projects’ site `.pth` files.
