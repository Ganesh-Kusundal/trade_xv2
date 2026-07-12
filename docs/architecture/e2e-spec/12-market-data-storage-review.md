# In-Depth Review: `market_data` Layout & Naming — Proposed Solution

**Date:** 2026-07-13  
**Scope:** Why root `market_data/` exists, what is wrong with the current design, and the correct target layout.  
**Related:** ADR-005 (exchange-agnostic datalake), E2E spec `08`/`09`, G3 backlog.

---

## 1. System intent (what this area is supposed to do)

TradeXV2 needs three distinct things:

| Concern | Purpose | Lifecycle |
|---|---|---|
| **Market data lake** | Hive Parquet OHLCV / options / indices for research, replay, analytics | Large, append-heavy, gitignored, relocatable |
| **Runtime state** | OMS orders, execution ledger, event log, tokens, live snapshots | Small, process-local, crash-recovery critical |
| **Exchange conventions** | Tick, lot, currency, paisa scale, calendar (NSE today) | Code / config — versioned in git |

Nautilus analogue: **ParquetDataCatalog path is configured externally**; the Python package never *is* the data. Conventions live in the model/adapters, not in a folder named like a dataset.

---

## 2. Current architecture map (as built)

```
Trade_XV2/
├── market_data/                 ← ~3.7 GB RUNTIME BLOB (gitignored)
│   ├── equities/ … parquet      ← lake (correct here in spirit)
│   ├── indices/ options/ …
│   ├── catalog.duckdb           ← lake catalog
│   ├── materialized/ momentum/  ← analytics derivatives
│   ├── oms_orders.sqlite        ← OMS (WRONG bucket)
│   ├── execution_ledger.sqlite  ← ledger default path (WRONG bucket)
│   ├── journal.sqlite           ← research journal (borderline)
│   ├── backtest_results.sqlite  ← research cache (borderline)
│   ├── events/                  ← event log dir (WRONG bucket)
│   └── live_snapshot.json       ← runtime (WRONG bucket)
├── .datalake/catalog.duckdb     ← SECOND catalog (split-brain risk)
├── runtime/                     ← tokens, event-log, dead_letter (partial overlap)
├── analytics_cache/             ← yet another cache root
└── src/
    ├── datalake/                ← code that reads/writes the lake
    ├── market_data/             ← MarketSurface *conventions* package (NOT data)
    └── domain/capabilities/market_surface.py  ← DIFFERENT type, same name
```

Canonical default:

```14:18:src/domain/ports/data_catalog.py
DEFAULT_DATA_ROOT: str = "market_data"
DEFAULT_CATALOG_PATH: Path = Path("market_data/catalog.duckdb")
```

Hardcoded siblings (not always going through that constant):

- `infrastructure/persistence/sqlite_order_store.py` → `market_data/oms_orders.sqlite`
- `infrastructure/persistence/sqlite_execution_ledger.py` → `market_data/execution_ledger.sqlite`
- `infrastructure/event_log.py` → `market_data/events`
- `datalake/research/journal.py`, `backtest_cache_store.py`, various `Path("market_data/...")` literals

`.gitignore` correctly treats `market_data/` as “Runtime data (created by the application)” — but then **OMS + ledger + events** are stuffed into a directory whose name means “historical market quotes.”

---

## 3. End-to-end flow (how paths are used)

1. Process starts with **CWD = repo root** (assumed, rarely validated).
2. `DataLake(DEFAULT_DATA_ROOT)` / analytics / replay open Parquet under `./market_data/equities/...`.
3. DuckDB opens `./market_data/catalog.duckdb` — *and* some paths also know `.datalake/`.
4. OMS / ledger / event log independently open SQLite under the same `./market_data/` tree.
5. `from market_data.market_surface import MarketSurface` loads **code** from `src/market_data/` (on `pythonpath = ["src", "."]`), while IDE `@market_data` often jumps to the **data directory**.

**Silent failure modes:**

| Failure | Why it is silent / dangerous |
|---|---|
| CWD ≠ repo root | Relative `"market_data"` creates a *new empty lake* elsewhere; research “works” with no data |
| Dual DuckDB catalogs | Writers hit one DB, readers another → empty results / stale metadata |
| OMS DB next to 3.5 GB equities | Backup/delete “market data” can wipe order history; Docker volume mounts become ambiguous |
| Two `MarketSurface` types | `domain.capabilities.MarketSurface` = broker coverage lane; `market_data.MarketSurface` = tick/lot/currency. Same name, different meaning → wrong import at review time |
| `domain` imports `market_data` package | Layering smell: domain constants pull a sibling package that exists only to avoid importing domain (circular-avoidance hack) |

---

## 4. Invariant checklist

| Invariant | Status |
|---|---|
| Code under `src/`; mutable datasets outside package | ✅ for lake *location*, ❌ for naming/clarity |
| One authoritative data root from config | ❌ string literal `"market_data"` scattered; no `AppConfig.data_root` |
| Lake ≠ OMS ≠ credentials | ❌ co-located under one folder |
| One DuckDB catalog | ❌ `market_data/catalog.duckdb` + `.datalake/catalog.duckdb` |
| Exchange conventions via ADR-005 ports / plugin | ⚠️ contracts exist; `src/market_data` is a stopgap; dual `MarketSurface` names |
| Gitignore excludes large binaries | ✅ `market_data/` ignored |

---

## 5. Failure & risk points (money-relevant)

1. **Operator deletes `market_data/` to “free disk”** → loses OMS SQLite + ledger + event log along with Parquet. Real-money audit trail gone.
2. **CI / Docker** copies or mounts “market_data” expecting only candles → accidentally persists or excludes OMS state incorrectly.
3. **Replay/backtest** depends on lake path; live recovery depends on ledger path — sharing a root couples unrelated failure domains.
4. **Import confusion** in agents/reviews: “fix market_data” sounds like a storage API; it is actually NSE tick conventions.

---

## 6. Proposed correct architecture

### 6.1 Separate three roots (Nautilus-aligned: catalog path ≠ package ≠ state)

```
${TRADEX_HOME}/                    # or repo-relative defaults for local dev
├── lake/                          # WAS market_data/equities|indices|options|…
│   ├── equities/
│   ├── indices/
│   ├── options/
│   ├── curated/                   # curated layout (already named in constants)
│   ├── materialized/
│   └── catalog.duckdb             # THE only DuckDB catalog for the lake
├── state/                         # WAS mixed into market_data + runtime/
│   ├── oms/
│   │   ├── orders.sqlite
│   │   └── execution_ledger.sqlite
│   ├── events/                    # event log
│   ├── research/
│   │   ├── journal.sqlite
│   │   └── backtest_results.sqlite
│   └── live_snapshot.json
└── secrets/                       # tokens stay under runtime/ or state/auth/
```

Local-dev default (still outside `src/`):

```
./data/lake/
./data/state/
```

Optional env / `AppConfig`:

```text
TRADEX_DATA_HOME=./data          # parent
TRADEX_LAKE_ROOT=${TRADEX_DATA_HOME}/lake
TRADEX_STATE_ROOT=${TRADEX_DATA_HOME}/state
```

### 6.2 Fix the code package (delete the name collision)

| Today | Target |
|---|---|
| `src/market_data/market_surface.py` (tick/lot/currency) | Fold into **NSE exchange plugin** +/or `domain` value object used by `ExchangeAdapter` (ADR-005). Interim: move to `src/domain/exchange/conventions.py` or `src/plugins/exchanges/nse/surface.py` |
| `domain.capabilities.MarketSurface` (coverage lane) | **Rename** to `MarketCoverage` / `CoverageLane` to end the homonym |

`domain.constants.market` must stop importing `market_data.*`; it should import domain/plugin conventions only (restores layering).

### 6.3 Single path authority

- Extend `AppConfig` (or `DataPaths` value object in `domain/ports/data_catalog.py`) with `lake_root`, `state_root`, `catalog_path`.
- All writers/readers take injected roots — **no** new `Path("market_data/...")` literals.
- Arch test: grep forbids `Path("market_data` and string `"market_data/"` outside migration shims + `.gitignore`.
- Delete or symlink-away `.datalake/` after consolidating catalog.

### 6.4 Why lake stays outside `src/` (unchanged principle)

Correct: large mutable Parquet must not live under the installable package.  
Wrong today: using the folder name `market_data` for *everything* including OMS, and shadowing a Python package of the same name.

---

## 7. Migration plan (minimal but correct)

### Phase 0 — Document & freeze (this ADR-style note)
- Accept layout: `data/lake` + `data/state`; rename coverage type; retire `src/market_data` package name.

### Phase 1 — Config spine (no data move yet)
1. Add `DataPaths` / `AppConfig` fields; wire composition root.
2. Make OMS, ledger, event_log, DataLake read from `DataPaths` (defaults still point at current files for zero downtime).
3. Arch grep test for new literals.

### Phase 2 — Physical split (local + docs)
1. Create `data/lake` and `data/state`.
2. Move Parquet + `catalog.duckdb` → `data/lake/`.
3. Move `oms_orders.sqlite`, `execution_ledger.sqlite`, `events/`, `live_snapshot.json` → `data/state/…`.
4. Move research sqlite → `data/state/research/`.
5. Leave `market_data/` as a **compat symlink** (`market_data` → `data/lake` for Parquet-only paths) **or** a thin shim directory with README “deprecated” for one release.
6. Remove `.datalake/` after verifying one catalog.

### Phase 3 — Naming cleanup
1. Rename `domain.capabilities.MarketSurface` → `MarketCoverage`.
2. Relocate tick/lot surface into exchange plugin; delete `src/market_data/`.
3. Update ADR-005 implementation (G3) to consume plugin, not `src/market_data`.

### Phase 4 — Hard cut
1. Remove compat symlink; defaults are `data/lake` + `data/state` only.
2. Update `.gitignore` (`/data/`, drop ambiguous `market_data/` once gone).
3. Docker/compose volume: mount `data/lake` and `data/state` separately (lake can be large read-mostly; state is small and backup-critical).

---

## 8. Expected Behavior Contract (post-fix)

| | Lake | State |
|---|---|---|
| **Inputs** | Ingestion / sync / curated migration | OMS, ledger, event bus persistence |
| **Outputs** | Parquet + single DuckDB catalog | SQLite / JSON recovery artifacts |
| **Timing** | Append-friendly; readers via DuckDB | Sync on order path before ACK where required |
| **Failure** | Missing lake → research fails clearly; live trading may continue if not needed | Missing state → **fail boot** in LIVE (no silent empty OMS) |
| **Backup** | Optional / regenerable from brokers | **Mandatory** for real-money audit |

---

## 9. Answers (review lens)

**What can go wrong silently?**  
Wrong CWD creates an empty lake; dual catalogs disagree; deleting “market data” wipes OMS/ledger; IDE/agent confuses data dir with `src/market_data` package.

**What breaks under real-time / ops?**  
Volume mounts and backups treat one folder as both disposable history and critical order state.

**Unsafe assumptions?**  
“`market_data` always means the repo lake”; “one catalog.duckdb”; “domain can safely import `market_data` package.”

**Implicit vs explicit?**  
Path roots are implicit string defaults; package vs dataset homonym is implicit; OMS-in-lake is an unstated coupling.

---

## 10. Decision ask

Recommend **accepting §6–§7** as the storage ADR (follow-on to ADR-005).  

Do **not** move the lake under `src/`. Do **split** lake vs state, **rename** the conventions package/types, and **config-inject** all roots.

Implementation should start at Phase 1 (config spine) — smallest correct step before any bulk `mv`.
