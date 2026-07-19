# `src/runtime-dev/` Inventory

**Date:** 2026-07-19
**Author:** Task 1 (Architecture Discovery)

## Directory Structure

```
src/runtime-dev/
└── instruments/
    ├── instruments_2026-07-12.csv  (215,941 lines)
    ├── instruments_2026-07-13.csv  (215,941 lines)
    ├── instruments_2026-07-14.csv  (216,640 lines)
    ├── instruments_2026-07-15.csv  (216,995 lines)
    ├── instruments_2026-07-16.csv  (218,066 lines)
    ├── instruments_2026-07-17.csv  (217,800 lines)
    ├── instruments_2026-07-18.csv  (217,800 lines)
    └── instruments_2026-07-19.csv  (218,715 lines)
```

**Total:** 8 files, ~1.74M lines, 199 MB on disk.

## Contents

The directory contains **zero Python files**. It is purely a data cache directory holding daily snapshots of Indian exchange instrument lists (BSE, NSE, MCX). Each CSV contains ~215k-218k rows with columns like:

- `SEM_EXM_EXCH_ID` — exchange (BSE, NSE, etc.)
- `SEM_SMST_SECURITY_ID` — security ID
- `SEM_TRADING_SYMBOL` — e.g. `USDINR-28Aug2024-FUT`
- `SEM_EXPIRY_DATE`, `SEM_STRIKE_PRICE`, `SEM_OPTION_TYPE`
- `SEM_LOT_UNITS`, `SEM_TICK_SIZE`, `SEM_EXCH_INSTRUMENT_TYPE`

## Git Status

- The entire `src/runtime-dev/` directory is **gitignored** — files are not tracked.
- No git history exists for these files.

## Production Code References

Three files reference `runtime-dev`:

| File | Line(s) | Usage |
|------|---------|-------|
| `src/brokers/dhan/loader.py` | 69 | Default cache directory for instrument data |
| `src/interface/ui/commands/cache_management.py` | 34, 88, 140 | Cache status, cleanup, and refresh commands |

One additional reference (`src/datalake/ingestion/sync_options.py:59`) points to a **different** project path (`Trade_J/runtime-dev/historical.duckdb`) and is unrelated.

### How production code uses this directory

1. **`dhan/loader.py`** — `InstrumentLoader` writes daily CSV snapshots here after fetching from the Dhan API. It also enforces a 7-day cleanup and 6-hour TTL cache.
2. **`cache_management.py`** — UI commands to display cache status, clear cache, and force-refresh instruments. All point to this same `runtime-dev/instruments` path.

## Assessment

| Aspect | Finding |
|--------|---------|
| **Is it code?** | No — pure CSV data cache |
| **Is it imported?** | No Python imports; 3 files reference the path as a data directory |
| **Does it duplicate `src/`?** | No — the actual code that manages it lives in `src/brokers/dhan/` |
| **Is it stale/experimental?** | No — actively used by production broker integration |
| **Should it be in `src/`?** | **No.** This is a cache/data directory, not source code |

## Recommendation: **RELOCATE** (not delete)

The `runtime-dev/` name is misleading — it suggests experimental runtime code, but it's actually a **data cache** used in production. The name `runtime-dev` was likely chosen because the directory sits at the project root level as a sibling to `src/`, but it was placed *inside* `src/` by accident.

### Proposed action

1. **Move** `src/runtime-dev/` → `data/instruments/` (or `cache/instruments/`)
2. **Update** the 3 hardcoded path references in:
   - `src/brokers/dhan/loader.py:69`
   - `src/interface/ui/commands/cache_management.py:34, 88, 140`
3. **Add** `data/instruments/` to `.gitignore` (already ignored via parent `runtime-dev`)
4. **Optionally** add `DHAN_CACHE_DIR` env var usage as the primary config mechanism (the code already supports it as a fallback)

This removes a confusing `src/` subdirectory while preserving the functional data cache the broker integration depends on.

### Why not delete

Deleting would break the Dhan broker integration — the loader and cache management commands rely on these cached instrument files for offline/local operation. The 7-day TTL cleanup already manages retention automatically.

### Why not keep as-is

The name `runtime-dev` inside `src/` is architecturally misleading. It violates the principle that `src/` should contain only source code, not runtime data artifacts.
