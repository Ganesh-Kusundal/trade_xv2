# OE-01 — Views vs Pipeline Ownership Decision

**Date:** 2026-07-20  
**Status:** Decision recorded (no deletion until parity proof)  
**Finding:** OE-01 — `src/analytics/views/` (~1.9k LOC) parallels Python `FeaturePipeline` scanners.

---

## Problem

Two scanner/feature paths exist:

| Path | Location | Driver |
|------|----------|--------|
| SQL views | `src/analytics/views/` | DuckDB materialized views at catalog refresh |
| Python pipeline | `src/analytics/pipeline/` | In-process FeaturePipeline on DataFrames |

Both produce scanner inputs. Duplication risks drift (indicator semantics, gap handling, session boundaries).

---

## Decision (Phase 4d)

**Canonical for operator PARITY paths:** Python `FeaturePipeline` + `StrategyPipeline` at composition root (`runtime/paper_session`, orchestrator).

**Canonical for datalake-at-scale / MCP / batch:** SQL views stack (`analytics/views/`) when query pushdown beats in-memory scans.

**Rule:** New features land in `domain/indicators/` first; pipeline wraps domain; views SQL may lag but must document equivalence gap in `QualityViews` materialization notes.

**Not in scope yet:** Deleting either stack. Deletion requires golden-dataset parity proof (same symbol/window → same feature columns ± floating tolerance).

---

## Exit criteria before deletion

1. One golden parity test: views query vs pipeline compute on fixed parquet window.
2. `architecture.md` ownership table updated.
3. MCP tools route through `datalake/quality/contract.py` for validation semantics (DP-05).

---

## Migration trigger

When PRE-DEPLOY live ≥ 8.5 **and** parity test green for NIFTY50 universe sample → deprecate the non-canonical path for that use case only (not global delete).
