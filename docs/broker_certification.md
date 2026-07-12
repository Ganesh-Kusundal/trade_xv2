# Broker Certification Report

The TradeXV2 broker certification suite validates that every broker plugin implements the full surface area expected by the framework — from authentication through market data, order lifecycle, portfolio, performance, and recovery.

---

## 1. What the Certification Suite Checks

The `BrokerCertifier` class (`brokers.certification.suite`) runs **30 checks** across 9 areas. Each check exercises a real API call through the `BrokerSession` public surface.

### Authentication & Session (4 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Authentication | `AUTHENTICATION` | Session is authenticated (`status.authenticated`) |
| Token Refresh | `TOKEN_REFRESH` | Token refresh logic exists (live brokers only; skipped for paper) |
| Token Expiry | `TOKEN_EXPIRY` | Token expiry handling exists (live brokers only) |
| Reconnect | `RECONNECT` | Session reconnect capability (live brokers only) |

> **Note:** Token refresh, expiry, and reconnect checks raise `NotImplementedError` for non-live brokers (paper, datalake). These are marked `warn_only` so they pass gracefully. Live-session checks are gated by the broker's `is_live` capability flag, never by broker name (DR-B2).

### Instrument & Symbol Mapping (5 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Symbol Lookup | `SYMBOL_LOOKUP` | `session.universe.equity("RELIANCE")` resolves to an instrument |
| Instrument Lookup | `INSTRUMENT_LOOKUP` | `session.stock("INFY")` returns correct symbol |
| Canonical Mapping | `CANONICAL_MAPPING` | Resolved instrument has `symbol == "RELIANCE"` |
| Security ID Mapping | `SECURITY_ID_MAPPING` | Instrument has a non-empty `id` |
| Reverse Mapping | `REVERSE_MAPPING` | Instrument's symbol round-trips back to original |

### Market Data (5 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Quote | `QUOTE` | `stock.refresh()` returns a quote with `ltp` |
| LTP | `LTP` | `stock.ltp` property returns a value after refresh |
| OHLC | `OHLC` | Quote contains open/high/low/close data |
| Depth | `DEPTH` | `stock.depth()` returns market depth data *(market hours only)* |
| Live Stream | `LIVE_STREAM` | `session.subscribe()` returns an active handle *(market hours only)* |

### Historical Data (4 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| 1-Minute | `TF_1M` | 30 days of 1m bars available *(warn_only)* |
| 5-Minute | `TF_5M` | 30 days of 5m bars available |
| 15-Minute | `TF_15M` | 30 days of 15m bars available *(warn_only)* |
| Daily | `TF_DAILY` | 90 days of daily bars available |

### Orders (4 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Market Order | `ORDER_MARKET` | `session.buy(stock, 1)` succeeds *(warn_only)* |
| Limit Order | `ORDER_LIMIT` | `session.buy(stock, 1, price=Decimal("1"))` succeeds *(warn_only)* |
| Cancel | `ORDER_CANCEL` | `session.cancel(order_id)` succeeds *(warn_only)* |
| Modify | `ORDER_MODIFY` | `session.modify(order_id, quantity=1)` succeeds *(warn_only)* |

> Paper broker validates order logic in simulation without real exchange orders.

### Portfolio (3 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Holdings | `HOLDINGS` | `account.holdings` returns data *(warn_only)* |
| Positions | `POSITIONS` | `account.positions` returns data *(warn_only)* |
| Funds | `FUNDS` | `account.funds` returns data |

### Performance (2 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Quote Latency | `QUOTE_LATENCY` | Measures `stock.refresh()` round-trip time in ms |
| Subscription Latency | `SUBSCRIPTION_LATENCY` | Measures subscribe round-trip time *(market hours only)* |

### Recovery & Rate Limits (3 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Disconnect | `DISCONNECT` | Disconnect handling exists (live only) |
| Session Recovery | `SESSION_RECOVERY` | Session recovery logic exists (live only) |
| Rate Burst | `RATE_BURST` | 5 rapid sequential quotes complete without error *(warn_only)* |

### Capability Matrix (2 checks)

| Check | CertArea | What it validates |
|-------|----------|-------------------|
| Rate Sustained | `RATE_SUSTAINED` | 3 sequential quotes complete without error *(warn_only)* |
| Capability Matrix | `CAPABILITY_MATRIX` | `stock.capabilities()` returns a list/tuple |

---

## 2. Certification Tiers (L0–L3)

Tiers are resolved automatically by `resolve_tier()` based on broker identity and context:

| Tier | Condition | Meaning |
|------|-----------|---------|
| **L0** | Reserved for future use | No certification — experimental |
| **L1** | `broker_id == "paper"` | Paper/synthetic broker — simulation only, no real exchange connectivity |
| **L2** | Any live broker (default) | Live broker in standard mode — real exchange data and order routing |
| **L3** | `live=True` flag passed | Live broker with full session management — token refresh, reconnect, recovery validated |

### Tier resolution rules

```python
from brokers.certification.schema_v2 import resolve_tier

resolve_tier("paper")        # → "L1"
resolve_tier("dhan")         # → "L2"
resolve_tier("dhan", live=True)  # → "L3"
```

### Status values

| Status | Meaning |
|--------|---------|
| `passed` | All checks passed |
| `failed` | One or more checks failed |
| `blocked` | Certification could not run (e.g. network unavailable) |

---

## 3. How to Run Certification

### CLI

```bash
# Paper broker (full suite, no credentials)
broker certify --broker paper

# Live broker (requires credentials)
broker certify --broker dhan

# Live session checks (L3 — token refresh, reconnect, etc.)
broker certify --broker dhan --live

# JSON output (for CI pipelines)
broker certify --broker paper --json

# Quick startup self-test (faster subset)
broker verify --broker paper
```

### Python SDK

```python
from brokers.session import BrokerSession
from brokers.certification import BrokerCertifier

session = BrokerSession("paper")
try:
    certifier = BrokerCertifier(session)
    report = certifier.certify()

    report.print_report()
    print(f"Certified: {report.is_certified}")
    print(f"Score: {report.passed}/{report.total}")
finally:
    session.close()
```

### MCP (for LLM agents)

```
broker_certify(broker="paper")
broker_verify(broker="paper")
```

### Supplementary checks

```bash
# Symbol mapping round-trip (7 asset/exchange combinations)
broker mappings --broker paper

# Market hours behavior matrix
broker market_hours --broker paper

# Full environment pre-flight (kubectl-style)
broker doctor --broker paper

# Health checks
broker health --broker paper

# Latency benchmark
broker benchmark --broker paper
```

---

## 4. How to Interpret the Report

### Console output

```
Certification — broker 'paper':
  [PASS] Authentication: authenticated
  [PASS] Token Refresh: not implemented (skipped)
  [PASS] Token Expiry: not implemented (skipped)
  [PASS] Reconnect: not implemented (skipped)
  [PASS] Symbol Lookup: RELIANCE -> NSE:RELIANCE
  [PASS] Quote: ltp=2450.5
  [PASS] Historical 5m: 150 5m bars
  [PASS] Order Market: market order placed
  [PASS] Quote Latency: 12.34ms
  ...
Overall: 30/30 passed -> CERTIFIED
```

### Reading each line

| Element | Meaning |
|---------|---------|
| `[PASS]` / `[FAIL]` | Check result |
| Check name | Matches `CertArea` enum value |
| Detail | Free-text result (e.g. `ltp=2450.5`, `150 5m bars`, `12.34ms`) |
| Latency (ms) | Shown in parentheses for performance checks |
| `off-market (skipped)` | Market-hours-gated check run outside trading hours |
| `not implemented (skipped)` | Live-only check on a non-live broker (`warn_only`) |

### JSON output (`--json`)

```json
{
  "schema_version": 2,
  "broker_id": "paper",
  "tier": "L1",
  "status": "passed",
  "is_certified": true,
  "passed": 30,
  "total": 30,
  "results": [
    {
      "area": "Authentication",
      "passed": true,
      "detail": "authenticated",
      "latency_ms": 0.42
    },
    ...
  ]
}
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed — broker is certified |
| `1` | One or more checks failed — broker is not certified |

---

## 5. How to Add New Certification Checks

### Step 1: Define the CertArea

In `brokers.certification.report`, add a new member to the `CertArea` enum:

```python
class CertArea(str, Enum):
    # ... existing areas ...
    MY_NEW_CHECK = "My New Check"
```

### Step 2: Implement the check function

In `brokers.certification.suite`, add a private function:

```python
def _my_new_check(s: BrokerSession) -> str:
    # Use only the public BrokerSession API
    result = s.some_method()
    if result is None:
        raise RuntimeError("check failed")
    return "detail string"
```

### Step 3: Register the check in `BrokerCertifier.certify()`

```python
def certify(self) -> CertificationReport:
    # ... existing checks ...
    report.add(self._check(CertArea.MY_NEW_CHECK, lambda: _my_new_check(s)))
    return report
```

### Step 4: Choose the check behavior

| Parameter | Effect |
|-----------|--------|
| `warn_only=True` | Failure doesn't block certification (used for optional features) |
| `market_hours_only=True` | Check is skipped outside NSE trading hours (9:15–15:30 IST) |
| Default | Check must pass for certification |

### Step 5: Update tests

Add a test in `tests/unit/brokers/certification/` that exercises the new check against the paper broker.

---

## 6. Market Hours Behavior

The certification suite respects NSE market hours via `is_nse_market_open()`:

### Market phases (IST)

| Phase | Time (IST) | Description |
|-------|-----------|-------------|
| `pre_market` | 09:00–09:15 | Pre-market session |
| `market_hours` | 09:15–15:30 | Normal trading session |
| `closing_auction` | 15:30–15:40 | Closing auction |
| `after_market` | 15:40–16:00 | After-market window |
| `weekend` | Sat–Sun | Non-trading day |
| `holiday` | Exchange holidays | Non-trading day |
| `open` | Before 09:00 | Pre-open (future phase) |
| `auction` | Auction periods | Special auction sessions |

### What's skipped off-market

| Check | Skipped off-market? |
|-------|-------------------|
| Depth | ✅ Yes |
| Live Stream | ✅ Yes |
| Subscription Latency | ✅ Yes |
| All others | ❌ No — run regardless of market hours |

### Behavior expectations per phase

| Phase | Quotes | History | Subscriptions | Orders |
|-------|--------|---------|---------------|--------|
| `market_hours` | ✅ | ✅ | ✅ | ✅ |
| `pre_market` | ✅ | ✅ | ✅ | ❌ |
| `closing_auction` | ✅ | ✅ | ✅ | ❌ |
| `after_market` | ✅ | ✅ | ❌ | ❌ |
| `weekend` | ✅ (cached) | ✅ | ❌ | ❌ |

### Force market hours (for CI)

```bash
FORCE_MARKET_OPEN=1 broker certify --broker paper
```

The `FORCE_MARKET_OPEN=1` environment variable forces `is_nse_market_open()` to return `True`, enabling market-hours-gated checks in CI pipelines that run outside trading hours.

---

## 7. Report Template (JSON Structure)

### Full certification report

```json
{
  "schema_version": 2,
  "broker_id": "string",
  "tier": "L1 | L2 | L3",
  "status": "passed | failed | blocked",
  "is_certified": true,
  "passed": 30,
  "total": 30,
  "results": [
    {
      "area": "string (CertArea value)",
      "passed": true,
      "detail": "string",
      "latency_ms": 0.42
    }
  ]
}
```

### Verify report (startup self-test)

```json
{
  "schema_version": 2,
  "broker_id": "string",
  "tier": "L1 | L2 | L3",
  "status": "passed | failed | blocked",
  "passed": true,
  "certified": true,
  "steps": [
    {
      "name": "string",
      "passed": true,
      "detail": "string"
    }
  ]
}
```

### Schema validation

Both report formats are validated by `brokers.certification.schema_v2`:

```python
from brokers.certification.schema_v2 import (
    validate_certification_report,
    validate_verify_report,
)

errors = validate_certification_report(report_dict)
# Returns empty list if valid, list of error strings if invalid
```

**Required fields for certification reports:** `schema_version`, `broker_id`, `tier`, `status`, `is_certified`, `passed`, `total`, `results`

**Required fields for verify reports:** `schema_version`, `broker_id`, `tier`, `status`, `passed`, `certified`, `steps`

---

## 8. Comparison Across Brokers

### Side-by-side JSON comparison

```bash
# Export reports for each broker
broker certify --broker paper --json > paper_cert.json
broker certify --broker dhan --json > dhan_cert.json
```

### Comparison matrix

| Dimension | Paper | Dhan | Upstox |
|-----------|-------|------|--------|
| **Tier** | L1 | L2 | L2 |
| **Authentication** | Simulated | OAuth2 + TOTP | OAuth2 |
| **Token Refresh** | Skipped (not live) | ✅ Live | ✅ Live |
| **Reconnect** | Skipped (not live) | ✅ Live | ✅ Live |
| **Depth Levels** | N/A | 20, 200 (WS) | 30 |
| **Market Feed** | Simulated | WebSocket | WebSocket V3 |
| **Super Orders** | N/A | ✅ | N/A |
| **Forever Orders** | N/A | ✅ | N/A |
| **News** | N/A | N/A | ✅ |
| **Option Chain** | Empty chain | Full chain | Full chain |

### What paper always passes

Paper broker passes all 30 checks because:

1. Authentication is simulated (always `authenticated`)
2. Symbol/instrument resolution uses the canonical registry
3. Quotes return simulated data
4. Orders execute in simulation (no real exchange)
5. History returns synthetic bar series
6. Token refresh / reconnect raise `NotImplementedError` → skipped via `warn_only`
7. Depth / live stream checks are `market_hours_only` and skipped outside trading hours

### Live broker differences

For live brokers (Dhan, Upstox), the following checks exercise real exchange connectivity:

- **Token Refresh / Expiry** — validates OAuth token lifecycle
- **Reconnect / Disconnect** — validates transport recovery
- **Depth / Live Stream** — real WebSocket connections (only during market hours)
- **Rate Burst / Sustained** — tests actual broker rate limits
- **Subscription Latency** — real WebSocket subscription timing

### Mapping certification

The `mappings` command runs a separate round-trip validation for 7 asset/exchange combinations:

```bash
broker mappings --broker paper
```

Output:

```
  [PASS] equity/NSE RELIANCE: round-trip ok (NSE:RELIANCE)
  [PASS] equity/BSE RELIANCE: round-trip ok (BSE:RELIND)
  [PASS] index/NSE NIFTY: round-trip ok (NSE:NIFTY)
  [PASS] future/NFO NIFTY: round-trip ok (NFO:NIFTY)
  [PASS] option/NFO NIFTY: round-trip ok (NFO:NIFTY)
  [PASS] currency/NSE USDINR: round-trip ok (NSE:USDINR)
  [PASS] commodity/MCX GOLD: round-trip ok (MCX:GOLD)
Overall: PASS
```

---

*Generated for Phase 4 — Task D4.8 of the Transformation Roadmap.*
