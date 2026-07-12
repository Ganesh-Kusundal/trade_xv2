# ADR-004: DuckDB for Analytical Queries

## Status

Accepted

## Context

The platform needs to run analytical queries over historical market data, trade history, and performance metrics. These queries are read-heavy, involve aggregation, joins, and window functions, and operate over Parquet files in the data lake.

SQLite is not optimized for analytical workloads. Pandas was historically used but creates domain purity issues (see `test_domain_no_pandas_import.py`). The analytics engine needs a columnar query engine that can query Parquet directly.

## Decision

Use **DuckDB** (`infrastructure/db/duckdb_pool.py`) as the analytical query engine:

1. DuckDB reads Parquet files directly from the data lake without materialization.
2. Query results are returned as domain-compatible types (not raw DataFrames leaking into domain code).
3. DuckDB is used only in `infrastructure/analytics` and `datalake` layers — never imported by domain or application layers.
4. The data lake follows a curated `.datalake` layout with partitioned Parquet files.

### Domain purity constraint

Core domain modules must import without pandas or DuckDB in `sys.modules` (enforced by `test_domain_no_pandas_import.py`). Export adapters that bridge DuckDB results to domain types live in `infrastructure/`, not `domain/`.

## Consequences

**Positive:**
- Columnar engine optimized for analytical queries over Parquet.
- No pandas dependency leak into domain layer.
- Single analytical query engine (no competing implementations).

**Negative:**
- DuckDB is a single-process engine (acceptable for current deployment).
- Requires Parquet file layout discipline in the data lake.

## Enforcement

- `tests/architecture/test_domain_no_pandas_import.py` — no top-level pandas in domain; cold-start import test
- `tests/architecture/test_datalake_no_analytics_imports.py` — datalake layer isolation
- `tests/architecture/test_import_direction_and_layering.py` — datalake/analytics not import cli
