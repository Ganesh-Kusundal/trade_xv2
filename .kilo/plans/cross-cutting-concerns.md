# Cross-Cutting Concerns Remediation Plan — Trade_XV2

## Executive Summary
Cross-cutting concerns (logging, error handling, configuration, resilience, auth, security, async) are fragmented across three broker adapters and lack centralized infrastructure. This plan addresses the highest-impact gaps in implementation-ready chunks.

---

## Priority Matrix

| # | Area | Severity | Effort | Impact |
|---|------|----------|--------|--------|
| 1 | Central Logging Bootstrap | HIGH | Medium | HIGH |
| 2 | Error Handling Standardization | HIGH | Medium | HIGH |
| 3 | Centralized Resilience Layer | HIGH | High | HIGH |
| 4 | Auth Token Security Hardening | HIGH | Medium | HIGH |
| 5 | Security Hardening | MEDIUM-HIGH | Medium | HIGH |
| 6 | Configuration Centralization | MEDIUM | Medium | MEDIUM |
| 7 | Async Thread Safety | MEDIUM | High | MEDIUM |

---

## Phase 1: Central Logging Bootstrap

### 1.1 Create centralized logging config module

**New file:** `brokers/common/logging_config.py`

```python
"""
Central logging configuration for Trade XV2.
Replaces scattered basicConfig() calls with a single dictConfig.
"""
import logging
import sys
import os
from pathlib import Path
from logging.config import dictConfig

def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    ...
```

**What it does:**
- Single `dictConfig` with a `StreamHandler` (stderr) and optional `FileHandler`
- Default formatter uses `%(asctime)s %(name)s %(levelname)s %(message)s`
- JSON formatter path ready for structlog migration
- Root logger level from env `XV2_LOG_LEVEL` (default INFO)
- Third-party library noise silenced (`urllib3`, `websockets`, `aiohttp` → WARNING+)
- Called once from `cli/main.py` before any other imports that log

**Files to modify:**
- Remove inline `basicConfig` from:
  - `datalake/migrate_options.py:33`
  - `datalake/sync_options.py:54`
  - `cli/commands/options_sync.py:11`
  - `scripts/clean_indices.py:118`
  - `scripts/refresh_stale_symbols.py:108`
  - `datalake/run_backtest.py:36`
  - `datalake/normalize.py:171`
  - `brokers/upstox/auth/login.py:178`
- Replace `print()` with `logger` calls in:
  - `check_data_freshness.py`
  - `datalake/monitor.py` (report section)
  - `scripts/test_depth_websocket.py`
  - `scripts/test_live_depth.py`
  - `scripts/verify_event_replay.py`

**Files to modify (normalize logging style):**
- `brokers/dhan/depth_20.py` — move `connected`/`started` to DEBUG
- `brokers/dhan/depth_200.py` — same
- `brokers/common/intelligent_gateway.py:89` — broker fallback from WARNING to INFO (expected failover)

---

## Phase 2: Error Handling Standardization

### 2.1 Create centralized exception hierarchy

**New file:** `brokers/common/exceptions.py`

```python
"""
Canonical exception hierarchy for all Trade XV2 modules.
All domain exceptions inherit from TradeXV2Error.
"""
class TradeXV2Error(Exception): ...
class BrokerError(TradeXV2Error): ...
class RetryableError(BrokerError): ...
class NonRetryableError(BrokerError): ...
class RateLimitError(BrokerError): ...
class CircuitBreakerOpenError(BrokerError): ...
class AuthenticationError(BrokerError): ...
class InstrumentNotFoundError(BrokerError): ...
class OrderError(BrokerError): ...
class DataError(TradeXV2Error): ...
class ConfigError(TradeXV2Error): ...
```

**Migration tasks:**
- Make `UpstoxApiError` in `brokers/upstox/auth/exceptions.py:6` inherit from `BrokerError` instead of `RuntimeError`
- Replace `NotImplementedError` usage at broker gateway boundaries (`upstox/gateway.py:128,257`, `dhan/gateway.py` read-only modes) with `NotSupportedError(BrokerError)`
- Create `datalake/exceptions.py` with `DatalakeError`, `DataValidationError`, `ConnectionError`

### 2.2 Add error code constants file

**New file:** `brokers/common/error_codes.py`

```python
"""
Centralized error codes for all modules.
Format: MODULE_ERR_DESCRIPTION
"""
...
```

Reference `DH-906` and `DH-808` from `brokers/dhan/http_client.py:271` as named constants.

### 2.3 Fix bare except / silent swallowing

**Files to fix:**
- `analytics/indicators/halftrend_backtest.py:215` — remove bare `except: pass`
- `cli/commands/benchmark.py:54,62,86,94,118,126` — log at minimum
- `cli/commands/dashboard.py:45,54,63,73,83` — log at minimum
- `brokers/common/event_log.py:77-78,93-94` — log warning on deserialization failure
- `brokers/common/observability/http_server.py:335` — log on cleanup failure
- `brokers/upstox/instruments/loader.py:145-146` — distinguish "not found" from "permission denied"
- `brokers/dhan/resolver.py:57-58` — distinguish `InstrumentNotFoundError` from unexpected errors

### 2.4 Standardize exception wrapping at boundaries

- `brokers/common/intelligent_gateway.py:116` — raise `BrokerError` instead of `RuntimeError` when all brokers fail
- `brokers/common/services/instrument_registry.py:140` — raise `InstrumentNotFoundError` instead of plain `ValueError`

---

## Phase 3: Centralized Resilience Layer

### 3.1 Wire RetryExecutor into Upstox HTTP client

**Files to modify:**
- `brokers/upstox/auth/http.py:124-176` — wrap `_request()` through `RetryExecutor` + rate limiter
- `brokers/upstox/auth/oauth_client.py` — add retry on transient failures, don't return -1 silently
- `brokers/upstox/auth/context.py:89-128` — remove dead code (CB + RetryExecutor created but never used); inject into `UpstoxHttpClient`

### 3.2 Eliminate duplicate retry in Dhan HTTP client

- `brokers/dhan/http_client.py:211-300` — replace inline retry loop with `RetryExecutor`; keep token-refresh callback pattern but delegate backoff to the shared framework

### 3.3 Add datalake I/O resilience

**Files to modify:**
- `datalake/duckdb_utils.py:34` — add timeout parameter to `duckdb.connect()`
- `datalake/io.py` — wrap file reads with `RetryExecutor`
- `datalake/loader.py` — add retry on network fetch
- `datalake/updater.py` — add retry on parquet writes
- `datalake/journal.py` — add retry on SQLite lock (already partially handled)

### 3.4 Normalize timeout granularity

- Introduce `connect_timeout` and `read_timeout` as separate parameters in `RetryExecutor` and all HTTP clients; current `timeout=15` is a single value covering both phases

---

## Phase 4: Auth Token Security Hardening

### 4.1 Move tokens from query strings to headers/body

- `brokers/dhan/factory.py:271-273` — change TOTP token generation to POST body with `application/x-www-form-urlencoded`
- `brokers/dhan/depth_20.py:256` — move `token` and `clientId` from URL query into WebSocket subprotocol or auth message
- `brokers/dhan/depth_200.py:247` — same

### 4.2 Enforce file permissions on token state stores

- `brokers/common/core/auth.py:191-200` — add `mode=0o600` to `open()` in `JsonTokenStateStore`
- `brokers/upstox/auth/json_token_state_store.py:41-54` — add `mode=0o600`
- `brokers/dhan/factory.py:63` — already sets 0o600 on env files; extend to token state

### 4.3 Remove token logging in scripts

- `scripts/test_live_depth.py:183-184` — redact token; log only last 4 chars with `logger.debug("token_last4=...")`
- `brokers/upstox/auth/login.py:226-229` — write tokens to file, don't print to stdout

---

## Phase 5: Security Hardening

### 5.1 SQL injection prevention in analytics views

- `analytics/views/manager.py` — validate `view_name` against a regex whitelist (`^[a-zA-Z_][a-zA-Z0-9_]*$`) before f-string into SQL
- `analytics/views/validator.py` — same validation
- `datalake/loader.py:257-265` — validate `symbol` against `^[A-Z0-9]+$` before building filesystem paths
- `datalake/gateway.py:45-50` — same symbol validation

### 5.2 Rate limiting on observability HTTP server

- `brokers/common/observability/http_server.py` — add in-memory token bucket rate limit per IP (100 req/min default); add `X-RateLimit-*` headers

### 5.3 .env.upstox gitignore enforcement

- Add `.env.upstox` to `/Users/apple/Downloads/Trade_XV2/.gitignore`
- Audit and rotate any committed credential (one-time check via git history)

### 5.4 Input validation centralization

- Create `brokers/common/validation.py` with `validate_symbol()`, `validate_view_name()`, `validate_path_component()`
- Use consistently across `datalake/`, `analytics/`, and broker adapters

### 5.5 URL allowlist for `load_from_url`

- `brokers/dhan/loader.py:113-120` — restrict URL schemes to `https://` and whitelist domains

---

## Phase 6: Configuration Centralization

### 6.1 Create central settings dataclass

**New file:** `brokers/common/settings.py`

```python
"""
Central configuration dataclasses for Trade XV2.
Single source of truth for all timeouts, URLs, thresholds.
"""
from dataclasses import dataclass, field

@dataclass(frozen=True)
class TimeoutSettings:
    http_connect: float = 5.0
    http_read: float = 15.0
    ws_connect: float = 10.0
    ...

@dataclass(frozen=True)
class RetrySettings:
    max_attempts: int = 3
    base_delay_ms: int = 500
    max_delay_ms: int = 5000
    ...

@dataclass(frozen=True)
class CircuitBreakerSettings:
    ...
```

### 6.2 Refactor hardcoded URLs

- Create `brokers/common/endpoints.py` with all broker endpoint constants
- Replace inline strings in `dhan/factory.py`, `dhan/http_client.py`, `dhan/depth_20.py`, `dhan/depth_200.py`, `upstox/auth/urls.py`, `upstox/auth/config.py`, `upstox/instruments/loader.py`

### 6.3 Unify env loading

- Replace `brokers/common/env_loader.py` with `python-dotenv` calls (already a dependency)
- Document actual env file conventions in `config/CONFIG.md`
- Fix `.env.example` — remove `DHAN_REST_BASE_URL` (unused key) or implement it

### 6.4 Wire Upstox factory to use UpstoxSettingsLoader

- `brokers/upstox/factory.py:32-46` — replace `os.environ.get` calls with `UpstoxSettingsLoader.from_env()`

---

## Phase 7: Async Thread Safety

### 7.1 Normalize lock types

- `brokers/dhan/depth_20.py:83` — `threading.Lock()` → `threading.RLock()`
- `brokers/dhan/depth_200.py:82` — `threading.Lock()` → `threading.RLock()`
- `brokers/dhan/http_client.py:135` — `threading.Lock()` → `threading.RLock()`

### 7.2 Fix resource leak in DhanConnection.close()

- `brokers/dhan/connection.py:307-323` — add `_depth_20_feed.stop()` and `_depth_200_feed.stop()` calls; register them with lifecycle manager

### 7.3 Guard depth feed callback registration

- `brokers/dhan/depth_20.py:103-109` — protect `_depth_callbacks.append()` with `self._lock`
- `brokers/dhan/depth_200.py:103-109` — same
- `brokers/dhan/depth_20.py:427` — lock already snapshots; just add write-side lock

### 7.4 Fix Upstox websocket concurrent send

- `brokers/upstox/websocket/market_data_v3.py:179-185` — add `_send_lock` to serialize `_send_raw()` calls

### 7.5 Isolate event loops in background threads

- Refactor all `asyncio.new_event_loop()` + `asyncio.set_event_loop()` patterns to use `asyncio.run()` inside a wrapper function that passes the loop explicitly to components; never use `set_event_loop` in background threads

---

## Implementation Order

1. **Phase 1 (Logging)** — unblocks everything else; quick win
2. **Phase 2 (Errors)** — prerequisite for consistent resilience behavior
3. **Phase 3 (Resilience)** — highest production-stability impact
4. **Phase 5 (Security)** — blocking before any further deployments
5. **Phase 6 (Config)** — enables Phases 3 and 4 to use shared settings
6. **Phase 4 (Auth)** — depends on Phase 6 for centralized secrets handling
7. **Phase 7 (Async)** — highest risk of regressions, done last with dedicated review

---

## Validation Checklist

- [ ] `pytest tests/architecture/` passes (architecture tests enforce single-source rules)
- [ ] `ruff check` passes on all modified files
- [ ] `python -m cli.main doctor` runs cleanly
- [ ] No `print()` calls remain in `brokers/`, `datalake/`, `analytics/`, `scripts/`
- [ ] `.env.upstox` is gitignored
- [ ] No token/password in `git log --all --diff-filter=A -- '*env*'`
- [ ] No bare `except:` or `except Exception:` pass blocks in broker/adapter code
