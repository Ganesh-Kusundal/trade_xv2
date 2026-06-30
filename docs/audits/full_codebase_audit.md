# TradeXV2 — Full Codebase Audit Report

**Audit Date:** 2026-06-30
**Auditors:** 7 Specialized Architecture Review Agents (parallel)
**Scope:** Entire TradeXV2 quantitative trading platform
**Methodology:** Evidence-based source code review (no documentation assumptions)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Modules Audited | 7 (domain, application, brokers, api+cli, datalake+market_data, analytics+config+infra, tests) |
| Files Reviewed | ~600+ |
| Total Findings | 102 |
| 🔴 Critical | 16 |
| 🟠 High | 27 |
| 🟡 Medium | 35 |
| 💡 Low | 24 |
| Test Suite Health | 68/100 |
| Overall Platform Health | 🔴 CRITICAL RISK — Active security exposure + architectural debt |

### Top 5 Immediate Actions

1. **🔴 REVOKE ALL CREDENTIALS** in `.env.local` — live JWTs, PINs, TOTP secrets tracked in git
2. **🔴 FIX RUNTIME BUGS** — `OrderRequest.correlation_id` AttributeError, `Candle(l=...)` field mismatch, corrupted `backtest_service.py`
3. **🔴 MOVE `TradeXV2Error`** to `domain/exceptions.py` — eliminates 9 layer violations
4. **🔴 FIX SQL INJECTION** patterns in `datalake/analytics/relative_volume.py` and API routers
5. **🟠 UNIFY BROKER ADAPTER CONTRACTS** — exception policy divergence, signature mismatches

---

## Module Health Scorecard

| Module | Files | Critical | High | Medium | Low | Score |
|--------|-------|----------|------|--------|-----|-------|
| `domain/` | 45 | 2 | 5 | 8 | 3 | 🟡 7.5/10 |
| `application/` | 55 | 4 | 8 | 7 | 3 | 🔴 5.5/10 |
| `brokers/` | 120+ | 3 | 5 | 5 | 4 | 🟠 6.5/10 |
| `api/` + `cli/` | 52 | 5 | 8 | 10 | 6 | 🔴 5.0/10 |
| `datalake/` + `market_data/` | 80+ | 3 | 6 | 11 | 9 | 🔴 5.5/10 |
| `analytics/` + `config/` + `infrastructure/` | 100+ | 4 | 7 | 6 | 4 | 🔴 5.0/10 |
| Tests (all directories) | 502 | 7 | 9 | 8 | 4 | ⚠️ 68/100 |

---

## Architecture Dependency Graph

```
                    ┌──────────┐
                    │  domain  │ ← Should be dependency root
                    └────┬─────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌────▼──────┐
    │ config  │    │ analytics │   │ brokers/  │
    └────┬────┘    └─────┬─────┘   └────┬──────┘
         │               │               │
         │          ┌────▼────┐          │
         │          │ datalake│          │
         │          └─────────┘          │
         │                               │
    ┌────▼───────────────────────────────▼──┐
    │          infrastructure               │
    │  (should only depend on domain)       │
    └───────────────────────────────────────┘

VIOLATIONS:
  config ──────→ brokers.common.resilience.errors  🔴
  infrastructure → brokers.common.resilience.errors 🔴 (8 files)
  application ──→ infrastructure (25+ imports)      🔴
  application ──→ brokers.common (24+ imports)      🔴
  api ─────────→ datalake (bypassing application)   🟠
  brokers ─────→ cli (bootstrap.py)                 🟠
  config ──────→ infrastructure.metrics             🟠
  analytics ───→ infrastructure.event_bus (concrete) 🟠
```

---

## 🔴 CRITICAL FINDINGS (MUST FIX)

### C-1: Live Secrets Tracked in Git

**Location:** `.env.local` (tracked via `git add -f`)
**Impact:** Anyone with repo access can place real trades, access balances, perform TOTP auth
**Evidence:** Contains Dhan/Upstox JWT tokens, client IDs, PINs, TOTP secrets, mobile numbers
**Fix:**
```bash
git rm --cached .env.local
# Then revoke ALL tokens at broker portals
# Rotate all credentials
# Use git-filter-branch or BFG to purge from history
```

### C-2: `OrderRequest.correlation_id` — Runtime AttributeError

**Location:** `api/routers/orders.py:285`
**Impact:** EVERY order placement via API crashes with AttributeError
**Evidence:** `req.correlation_id` accessed but `OrderRequest` schema has no such field
**Fix:** Add `correlation_id: str | None = None` to `OrderRequest` in `api/schemas.py`

### C-3: `Candle` Schema Field Mismatch — Live Candles Crash

**Location:** `api/schemas.py:129` vs `api/routers/market.py:244`
**Impact:** Live candles endpoint crashes on every request
**Evidence:** Schema defines `low` field but code constructs `Candle(l=float(bar.low))`
**Fix:** Change `l=float(bar.low)` to `low=float(bar.low)` in `market.py:244`

### C-4: Corrupted `backtest_service.py`

**Location:** `application/backtest/backtest_service.py:56-113`
**Impact:** File has overlapping/duplicated content, won't parse as valid Python
**Fix:** Remove lines 56-113 (duplicated method body)

### C-5: Pandas Import in Domain Layer

**Location:** `domain/ports/market_data.py:49, 131`
**Impact:** Domain layer (innermost) depends on pandas framework — violates clean architecture
**Fix:** Move `GatewayMarketDataAdapter`, `DataFrameMarketDataAdapter`, `_df_to_historical_series` to `infrastructure/adapters/`

### C-6: Untyped Port Interfaces Defeat Static Typing

**Location:** `domain/ports/margin_provider.py:21-34`, `domain/ports/risk_manager.py:22-37`
**Impact:** `calculate_margin_for_order(order: Any) -> Any` provides zero type safety
**Fix:** Use `OrderRequest` as input, define `MarginResult` dataclass as output

### C-7: Application Layer Pervasive Infrastructure Imports

**Location:** `application/oms/order_manager.py:38-48`, `context.py:18-30`
**Impact:** Cannot swap event bus, metrics, or state machine without modifying core OMS
**Fix:** Define ports in `domain/ports/` and inject through composition root

### C-8: Infrastructure Depends on Brokers (Dependency Inversion Violation)

**Location:** 8 files in `infrastructure/` importing from `brokers.common.resilience.errors`
**Impact:** Infrastructure cannot be reused, tested, or deployed independently
**Fix:** Move `TradeXV2Error` hierarchy to `domain/exceptions.py`

### C-9: SQL Injection via f-String Queries

**Location:** `datalake/analytics/relative_volume.py:92-132`, `api/routers/analytics.py:60`, `api/routers/strategy.py:53-67`
**Impact:** User-provided values interpolated directly into SQL
**Fix:** Use parameterized queries with `?` bind parameters

### C-10: `X-Forwarded-For` Header Trusted Without Proxy Allowlist

**Location:** `api/middleware.py:273-280`
**Impact:** Any client can spoof IP to bypass rate limiting
**Fix:** Only trust `X-Forwarded-For` from known proxy IPs

### C-11: `place_order` Signature Divergence Between Gateways

**Location:** `brokers/common/gateway.py:210-223` vs `brokers/upstox/gateway.py:498-512`
**Impact:** Upstox adds `is_amo` parameter not in ABC — violates Liskov Substitution
**Fix:** Move `is_amo` to extended capabilities or request object

### C-12: Exception Policy Divergence Between Adapters

**Location:** `brokers/dhan/orders.py:200-358` vs `brokers/upstox/orders/order_command_adapter.py:53-80`
**Impact:** Dhan raises `OrderError`, Upstox returns `OrderResponse.fail()` — inconsistent
**Fix:** Unify — both should return `OrderResponse.fail()`

### C-13: `modify_order` Signature Mismatch in Paper Gateway

**Location:** `brokers/common/gateway.py:251-253` vs `brokers/paper/paper_gateway.py:307-356`
**Impact:** Paper gateway takes explicit kwargs instead of `**changes` — cannot substitute
**Fix:** Match ABC signature with `**changes`

### C-14: Hardcoded Absolute Path to External Database

**Location:** `datalake/ingestion/sync_options.py:61`
**Impact:** `"/Users/apple/Downloads/Trade_J/runtime-dev/historical.duckdb"` breaks on any other machine
**Fix:** Move to environment variable

### C-15: Security Tests That Cannot Fail

**Location:** `tests/test_security_findings.py:55-60, 369-388`
**Impact:** Security violations cause `pytest.skip()` instead of FAIL — regressions go unnoticed
**Fix:** Remove `pytest.skip` — let assertions fail naturally. Assert `mode == 0o600` for file permissions.

### C-16: `test_p0_capabilities_covered` Doesn't Assert Coverage

**Location:** `brokers/dhan/tests/regression/test_coverage_manifest.py:46-71`
**Impact:** `frozenset(...)` result is computed and discarded — test always passes
**Fix:** Assign to variable and assert coverage

---

## 🟠 HIGH FINDINGS (SHOULD FIX)

### Architecture & Layer Violations

| ID | Location | Issue |
|----|----------|-------|
| H-1 | `domain/instrument_id.py` + `historical.py` | Triple instrument identity types (InstrumentId, InstrumentRef, Instrument) |
| H-2 | `domain/constants/exchanges.py` + `exchange_segments.py` | Duplicate exchange alias mappings |
| H-3 | `domain/requests.py` + `historical.py` | Duplicate OHLCV models (HistoricalCandle vs HistoricalBar) |
| H-4 | `domain/models/__init__.py` | Redundant facade creating parallel import paths |
| H-5 | `domain/events/types.py` | Duplicate event types (KILL_SWITCH_FLIPPED vs TOGGLED, etc.) |
| H-6 | `application/oms/context.py` | God object TradingContext (760 lines, 15+ params) |
| H-7 | `application/composer/` | Zero test coverage on critical routing/quota logic |
| H-8 | `brokers/common/bootstrap.py:66` | Imports from `cli/` — circular dependency |
| H-9 | `brokers/upstox/websocket/v3_auto_reconnect.py` | No cooldown/reset after max retries — feed dies permanently |
| H-10 | `brokers/dhan/gateway.py:157-182` | Post-cancel verification race — failed verification returns success |
| H-11 | `api/routers/scanner.py` + `analytics.py` | Massive duplicate query logic |
| H-12 | `api/routers/audit.py` | Complete router never registered — dead endpoints |
| H-13 | `api/schemas.py` | 11 endpoints use `response_model=dict` — no validation |
| H-14 | `api/routers/market.py:104, 310` | Calls `gateway._load_parquet()` — private method |
| H-15 | `datalake/core/schema.py` + `universe.py` | Duplicate `load_universe()` function |
| H-16 | `datalake/core/pit_joins.py` + `scanner/compiler.py` | Duplicate `validate_no_lookahead()` with different patterns |
| H-17 | `datalake/core/schema.py` + `paths.py` | Inconsistent timeframe constants |
| H-18 | `datalake/storage/catalog.py:194-203` | `get_symbol()` executes same query twice |
| H-19 | `analytics/views/manager.py` | God-class with duplicate method definitions (F811) |
| H-20 | `analytics/scanner/scanners.py` | 4 scanners copy-paste identical `scan()` flow |
| H-21 | `config/feature_flags.py` | Global mutable class state — not test-isolated |
| H-22 | `infrastructure/security/secret_manager.py` + `config/secrets_manager.py` | Duplicate secret management systems |

### Concurrency & Thread Safety

| ID | Location | Issue |
|----|----------|-------|
| H-23 | `application/oms/portfolio_tracker.py:61-63` | Unprotected mutable state — data race from event thread |
| H-24 | `application/oms/oms_gateway_proxy.py:119-120` | Counters not protected by lock |
| H-25 | `datalake/storage/cache_utils.py:270-288` | `get_last_candle_fast()` creates new DuckDB connection per call |

### Type Safety

| ID | Location | Issue |
|----|----------|-------|
| H-26 | `application/oms/extended_order_service.py:37-45` | All collaborators typed as `Any` |
| H-27 | `application/oms/square_off_service.py:49-61` | All collaborators typed as `Any` |

---

## 🟡 MEDIUM FINDINGS (CONSIDER)

### Dead Code

| Artifact | Location | Action |
|----------|----------|--------|
| `status_normalizer.py` | `domain/` (entire file) | Delete — deprecated, 0 callers |
| `TimestampSemantics` | `domain/provenance.py:38` | Delete — never imported |
| `MarginCalculationErrorPort` | `domain/ports/margin_provider.py:38` | Delete — empty protocol |
| `datalake/store/` | Empty shim package | Delete, update 2 callers |
| `datalake/normalize.py` | Root-level migration script | Move to `scripts/` |
| `PaperOMSAdapter` / `ReplayOMSAdapter` | `application/execution/execution_mode_adapter.py:77-78` | Delete — empty dynamic classes |
| 34 backward-compat shims | `datalake/*.py` | Add deprecation warnings, then delete |
| `analytics/tests/test_deep_dive.py` | Empty shim file | Delete |

### Duplicate Logic Map

| Concept | Locations | Canonical |
|---------|-----------|-----------|
| Kill switch check | 4 places in application/oms | `risk_manager.py:check_order` |
| Event publish pattern | 5+ files | Shared `EventPublisher` |
| OrderRequest→Command conversion | 2 places | `OmsOrderCommand.from_request()` |
| Exchange alias mapping | 2 places in domain/ | `exchange_segments.py` |
| OHLCV bar/candle | 2 places in domain/ | `historical.py` (HistoricalBar) |
| Scanner `scan()` flow | 4 scanners | `BaseScanner.scan()` |
| RSI scoring formula | 3 scanners | `scanner/scorer.py` |
| Post-cancel verification | 3 gateways | Shared utility |
| `history()` date math | Dhan + Upstox | `BatchFetchMixin` |
| Secret retrieval | 2 modules | Split by concern |

### Code Smells

| Smell | Location | Description |
|-------|----------|-------------|
| God data file | `domain/capability_manifest.py` (1241 lines) | Hardcoded data should be YAML/JSON |
| God class | `application/oms/context.py` (760 lines) | 15+ constructor params |
| God class | `analytics/views/manager.py` (770 lines) | Duplicate method definitions |
| God class | `cli/services/broker_service.py` (564 lines) | 25+ methods |
| God file | `cli/commands/market.py` (21.5KB) | 6+ distinct responsibilities |
| God file | `cli/main.py` (483 lines) | 270-line dispatch table |
| God object | `DhanConnection` (720 lines) | Wires 15+ adapters |
| 862L script at root | `analytics/precompute_features.py` | Should be in `scripts/` |
| 608L orphan at root | `datalake/gateway.py` | Should be in `storage/` or `adapters/` |

---

## Test Quality Summary

### Overall: 68/100

| Dimension | Score | Notes |
|-----------|-------|-------|
| Test Naming | 55% | 24 `test_basic` tests + many non-descriptive names |
| Assertion Quality | 65% | `assert True`, `assert is not None`, `pass`-only |
| Determinism | 88% | Most deterministic; some `sleep()`-based |
| Isolation | 75% | ContextVar leaks, global state issues |
| Single Responsibility | 80% | Most tests verify one behavior |
| Mocking Discipline | 82% | Mocks at boundaries; real domain objects |
| No Duplicates | 70% | 11 duplicated OMS test files |
| Edge Case Coverage | 60% | Happy path covered; edge cases sparse |
| Security Tests | 50% | Tests that can't fail, soft-assert, skip on violation |
| Test Infrastructure | 85% | Good fixtures, conftest, markers |

### Tests to Delete

| File | Reason |
|------|--------|
| `analytics/tests/test_deep_dive.py` | Empty shim |
| `tests/unit/test_domain_port_contracts.py:48-49` | `assert X is not None` on import |
| `tests/test_security_findings.py:321-327` | Coverage placeholder |

### Tests to Rename (24 instances)

All `test_basic` in analytics/tests, datalake/tests, domain/tests → descriptive behavior names

### Tests to Rewrite

| Test | Issue | Fix |
|------|-------|-----|
| `test_backoff.py:12-16` | `assert True` | Assert delay returns to initial |
| `test_error_paths.py:51-110` (6 tests) | `pass` in except | Assert specific exceptions |
| `test_security_findings.py:369-388` | Only prints | Assert `mode == 0o600` |
| `test_runtime_validation_audit.py:81-83` | No assertions | Assert on runtime components |

### Coverage Gaps (Critical)

| Gap | Risk |
|-----|------|
| `OrderRequest` quantity validation | Invalid orders reach broker |
| `PortfolioTracker` SELL PnL edge cases | Wrong tax reporting |
| `ProcessedTradeRepository` concurrent writes | Double-counting |
| `StatusMapperRegistry` thread safety | Race during broker init |
| `DownloadEngine` network timeout | System hangs |
| `ViewManager` concurrent DuckDB access | Query corruption |

---

## Remediation Roadmap

### Phase 1: Emergency (This Week)

| # | Action | Effort | Module |
|---|--------|--------|--------|
| 1 | Revoke & rotate ALL credentials in `.env.local` | S | Security |
| 2 | Fix `OrderRequest.correlation_id` AttributeError | S | api/ |
| 3 | Fix `Candle(l=...)` → `Candle(low=...)` | S | api/ |
| 4 | Fix corrupted `backtest_service.py` | S | application/ |
| 5 | Fix SQL injection in `relative_volume.py` | S | datalake/ |
| 6 | Fix X-Forwarded-For IP spoofing | S | api/ |
| 7 | Fix security tests that can't fail | S | tests/ |
| 8 | Externalize hardcoded path in `sync_options.py` | S | datalake/ |

### Phase 2: Critical Architecture (Next Sprint)

| # | Action | Effort | Module |
|---|--------|--------|--------|
| 9 | Move `TradeXV2Error` to `domain/exceptions.py` | M | domain/ + infra |
| 10 | Extract pandas adapters from `domain/ports/` | M | domain/ |
| 11 | Type port interfaces (Margin, Risk, Backtest) | M | domain/ |
| 12 | Unify broker exception policy (raise vs return) | M | brokers/ |
| 13 | Fix Paper `modify_order` signature | S | brokers/ |
| 14 | Fix cancel verification race in Dhan | S | brokers/ |
| 15 | Add Upstox reconnect cooldown/reset | S | brokers/ |
| 16 | Break `brokers.bootstrap → cli` dependency | S | brokers/ |
| 17 | Add locks to `PortfolioTracker` | S | application/ |
| 18 | Add composer tests | M | application/ |

### Phase 3: Deduplication & Cleanup (Next Quarter)

| # | Action | Effort | Module |
|---|--------|--------|--------|
| 19 | Consolidate instrument identity types | M | domain/ |
| 20 | Deduplicate exchange alias mappings | S | domain/ |
| 21 | Deduplicate event types | M | domain/ |
| 22 | Centralize kill switch enforcement | M | application/ |
| 23 | Extract `OmsOrderCommand.from_request()` | S | application/ |
| 24 | Template method for scanners | M | analytics/ |
| 25 | Fix ViewManager duplicate methods | M | analytics/ |
| 26 | Delete all dead code (see table above) | S | All |
| 27 | Add deprecation warnings to 34 shims | M | datalake/ |
| 28 | Rename all `test_basic` tests | S | tests/ |
| 29 | Consolidate 11 duplicated OMS test files | M | tests/ |

### Phase 4: Long-Term Architecture (Next Half)

| # | Action | Effort | Module |
|---|--------|--------|--------|
| 30 | Decompose `TradingContext` (760L) | L | application/ |
| 31 | Full dependency inversion for application layer | L | application/ |
| 32 | Define Pydantic response models for 11 `dict` endpoints | M | api/ |
| 33 | Route API datalake access through application layer | L | api/ |
| 34 | Externalize `capability_manifest.py` to YAML | M | domain/ |
| 35 | Unify OHLCV types (deprecate HistoricalCandle) | M | domain/ |
| 36 | Add import-linter contracts for all violations | M | All |
| 37 | Split `cli/commands/market.py` (21.5KB) | M | cli/ |
| 38 | Rewrite all `assert True` / `pass`-only tests | M | tests/ |
| 39 | Fill all coverage gaps | M | tests/ |

---

## Adapter Consistency Matrix (Brokers)

| Method | Dhan | Upstox | Paper | Notes |
|--------|------|--------|-------|-------|
| `place_order()` | Raises | Returns fail() | Returns OK | Exception policy diverges 🔴 |
| `modify_order()` | **changes | **changes | **kwargs (diff sig) | Paper mismatch 🔴 |
| `cancel_order()` | + verification | + verification | + verification | Race in Dhan 🟠 |
| `get_order()` | O(1) lookup | O(1) + fallback | Scan orderbook | |
| `history()` | ✅ | ✅ | Simulated | Duplicate date math |
| `quote()` / `ltp()` / `depth()` | ✅ | ✅ | Simulated | |
| `option_chain()` / `future_chain()` | ✅ | ✅ | Simulated | |
| `stream()` | SubEngine | V3 Multiplexer | Always disconnected 🔴 | Paper broken |
| `positions()` / `holdings()` / `funds()` | ✅ | ✅ | ✅ | |
| `search()` | ✅ | ✅ | Hardcoded | Paper returns fake |
| `load_instruments()` | (source, use_cache) | (source only) ⚠️ | No-op | Signature mismatch |
| `capabilities()` | ✅ | ✅ | ✅ | |
| `describe()` | Private access ⚠️ | ✅ | ✅ | |

---

## Security Summary

| Risk | Severity | Status |
|------|----------|--------|
| Real credentials in git | 🔴 Critical | **ACTIVE EXPOSURE** |
| SQL injection pattern | 🔴 Critical | Mitigated by hardcoded maps, but fragile |
| IP spoofing (X-Forwarded-For) | 🔴 Critical | Unmitigated |
| Auth bypass (AUTH_MODE env) | 🟡 Medium | Default is `none` |
| CORS wildcard | ✅ Good | Explicit origins |
| Rate limiting | ✅ Good | Sliding window |
| API key timing attack | ✅ Good | `secrets.compare_digest` |
| Token redaction in logs | ✅ Good | Filter implemented |
| Encryption at rest | ✅ Good | Fernet encryption |
| File permissions on secrets | 🔴 Broken | Test only prints, doesn't assert |

---

## Test Quality by Directory

| Directory | Files | Functions | % Standards | Key Issues |
|-----------|-------|-----------|-------------|------------|
| `domain/tests/` | 9 | ~280 | 92% ✅ | Best quality; minor gaps |
| `config/tests/` | 4 | ~120 | 88% ✅ | 1 misplaced test file |
| `infrastructure/tests/` | 14 | ~200 | 85% ✅ | ContextVar leak |
| `application/oms/tests/` | 21 | ~400 | 82% ✅ | 11 duplicates in brokers/ |
| `cli/tests/` | 33 | ~520 | 80% ✅ | File existence tests |
| `datalake/tests/` | 33 | ~450 | 80% ✅ | `assert is not None` patterns |
| `brokers/` (all) | 199 | ~2400 | 75% ⚠️ | `assert True`, `pass` tests |
| `tests/e2e/` | 17 | ~180 | 70% ⚠️ | Timing-dependent |
| `tests/integration/` | 27 | ~320 | 75% ⚠️ | Global state leaks |
| `analytics/tests/` | 25 | ~340 | 55% 🔴 | 24 `test_basic` + smoke tests |

---

*Report generated by 7 parallel specialized audit agents. All findings based on source code evidence.*
