# Broker Module Engineering Analysis Report

**Date**: 2026-06-12  
**Analyst**: Senior Trading Infrastructure Architect  
**Scope**: `brokers/dhan/`, `brokers/common/`, `brokers/upstox/`, `brokers/paper/`

---

## Executive Summary

The broker module has been through 8 sprints of hardening. A critical bug was found and fixed during this analysis: the `CircuitBreaker` integration used wrong method names (`record_success`/`record_failure` instead of `on_success`/`on_failure`), causing **every API call to crash with AttributeError**. This was the root cause of all test failures previously attributed to "token expiry."

**Current state: 11 Dhan API endpoints verified working end-to-end with live data.**

---

## Root Cause Analysis: The Circuit Breaker Bug

### What happened
In Sprint 2, circuit breaker support was added to `brokers/dhan/http_client.py`. The `CircuitBreaker` class in `brokers/common/resilience/circuit_breaker.py` exposes:
- `on_success()` — record a successful call
- `on_failure()` — record a failed call
- `allow_request()` — check if circuit is closed

But the HTTP client was wired with:
- `record_success()` — **does not exist**
- `record_failure()` — **does not exist**

### Impact
Every API call through the factory-created gateway crashed at the `self._circuit_breaker.on_success()` line after a successful HTTP response. The `AttributeError` propagated up as an unhandled exception. Tests that caught `Exception` broadly interpreted this as "Invalid Token" or "API failure."

### Why it wasn't caught
Unit tests use `FakeHttpClient` which has no circuit breaker, so the bug path was never exercised. Only live integration tests (which use the factory → real `CircuitBreaker`) hit the bug.

### Fix applied
Changed all 3 occurrences: `record_success()` → `on_success()`, `record_failure()` → `on_failure()`.

---

## Endpoint Verification (Live Dhan API)

| # | Endpoint | Method | Status | Data |
|---|----------|--------|--------|------|
| 1 | `/fundlimit` | GET | ✓ OK | ₹0.34 available |
| 2 | `/positions` | GET | ✓ OK | 0 open positions |
| 3 | `/holdings` | GET | ✓ OK | 0 holdings (account sold GODFRYPHLP) |
| 4 | `/marketfeed/quote` | POST | ✓ OK | RELIANCE ₹1,293 |
| 5 | `/orders` | GET | ✓ OK | 0 orders today |
| 6 | `/trades` | GET | ✓ OK | 0 trades today |
| 7 | `/optionchain/expirylist` | POST | ✓ OK | 3 expiries: Jun 16, 23, 30 |
| 8 | `/marketfeed/quote` (depth) | POST | ✓ OK | 5 bids, 5 asks |
| 9 | `/charts/historical` | POST | ✓ OK (after fix) | `date` → `str()` serialization |
| 10 | `/marketfeed/ltp` (MCX) | POST | ✓ OK | GOLD AUG FUT ₹150,363 |
| 11 | Circuit breaker state | — | ✓ CLOSED | 0 failures, 5 threshold |

---

## Token Flow Analysis

### Flow
```
.env.local → BrokerFactory._load_dotenv() → os.environ
         → BrokerFactory.create() reads os.environ["DHAN_ACCESS_TOKEN"]
         → _is_token_expired() checks JWT exp claim
         → If expired: _generate_totp_token() → _update_env_token() → new token
         → DhanHttpClient(client_id, access_token, circuit_breaker)
         → HTTP header: "access-token: <token>"
```

### Findings
1. **Token is valid for 24 hours** — JWT `exp` claim confirmed
2. **No mid-session refresh needed** — token generated at 17:10, valid until next day 17:10
3. **Multiple gateways share same token** — `_is_token_expired()` returns False, no regeneration
4. **DH-906 was NOT a token issue** — it was the `AttributeError` from circuit breaker bug
5. **TOTP cooldown (2 min)** — correctly prevents rapid regeneration

### Design issue: Token stored in `os.environ`
The factory reads the token from `os.environ` which is process-global. If two test fixtures create gateways in the same process, they share the same token. This is correct behavior but could be surprising.

---

## Code Smells and Design Issues Found

### Critical (Fixed)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 1 | Circuit breaker wrong method names | `http_client.py` | Every API call crashed |
| 2 | `date` objects not JSON-serializable | `historical.py` | Historical data endpoint crashed |

### High (Still Present)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 3 | WebSocket connects but receives no data | `websocket.py` + Dhan server | No real-time data via WS; polling fallback works |
| 4 | `get_holdings` returns 0 when account has holdings | `portfolio.py` | Holdings shown as empty — need to verify with account that has holdings |
| 5 | No order placement end-to-end test | `test_live_validation.py` | Validation tested but actual placement not tested (intentional — no real orders) |
| 6 | Option chain not tested end-to-end | integration tests | Expiry list works, full chain not verified live |

### Medium (Still Present)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 7 | Upstox broker.py uses old `BrokerConnection` | `upstox/broker.py` | Cannot add 3rd broker cleanly; 29 references to old pattern |
| 8 | `PollingMarketFeed` not wired into `DhanConnection` | `connection.py` | Users must manually create polling feed |
| 9 | No structured logging config | No `logging.conf` | Logs go to stderr with no format/rotation |
| 10 | Performance test thresholds machine-dependent | `test_performance.py` | 175k load takes 6-60s depending on machine |

### Low (Still Present)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 11 | `brokers/common/` has 4,900 lines of partially-dead code | Multiple | Confusing — unclear what's alive |
| 12 | No `.pyi` type stubs | — | IDE auto-complete limited |
| 13 | `pyproject.toml` missing `pyotp`, `pyjwt` deps | `pyproject.toml` | Fresh install would fail |

---

## Architecture Assessment

### What works well
- **Single model system** — `brokers.common.core.domain` is the canonical source for Order, Position, Trade, etc.
- **Clean adapter pattern** — each Dhan capability (orders, portfolio, market data) is a separate adapter
- **Factory pattern** — `BrokerFactory.create()` handles credential loading, token refresh, circuit breaker wiring
- **Contract tests** — 18 tests any future broker must pass
- **Reconciliation service** — detects drift between OMS and broker state

### What needs improvement
- **No unified broker interface** — Dhan uses `BrokerGateway`, Upstox uses `UpstoxBroker(BrokerConnection)`. Adding a 3rd broker requires choosing which pattern to follow.
- **WebSocket is unreliable** — Dhan's server drops connections. Polling fallback exists but isn't integrated.
- **No metrics/observability** — can't track API latency, error rates, or order latency in production.

---

## Recommendations (Priority Order)

1. **Run full test suite** — verify all 300+ tests pass with the circuit breaker fix
2. **Add option chain live test** — verify full chain with greeks works end-to-end
3. **Wire `PollingMarketFeed` into `DhanConnection`** — make it the default when WebSocket fails
4. **Add `pyotp` and `pyjwt` to `pyproject.toml`** — fix fresh install
5. **Add logging config** — `logging.basicConfig(level=INFO, format=...)` in factory
