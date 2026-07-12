# Phase 5 — Root Causes, Expected Behavior Contract, Ranked Findings

## Root cause consolidation

| Root cause | Manifestations | Evidence |
|------------|----------------|----------|
| **Fragmented composition roots** | Duplicate event buses, OMS double-registration warnings, API/CLI/SDK divergent bootstrap | `process_context.py`, 6+ roots in Phase 1 |
| **Missing authoritative execution spine** | Backtest `PURE_SIM`, paper synthetic fills, orchestrator dry-run default | `backtest/engine.py`, `trading_runtime_factory.py` |
| **Asymmetric broker integration** | Upstox no TICK publish; Upstox recon duplicates engine; Dhan-only gap backfill | `market_data_v3.py`, `upstox/reconciliation/service.py` |
| **Domain ↔ broker leakage** | `segment_mapper_for` in domain; breaks extensibility + import-linter | `domain/market/segment_mapper.py` |
| **Soft-fail / empty-state semantics** | Dropped ticks, datalake empty returns, `event_bus=None` no-ops | Phase 2 silent failure table |
| **Shallow reconciliation economics** | Status/qty compare only; `auto_repair` off by default | `reconciliation_engine.py` |
| **CI / certification untruthful** | 15+ stale paths, warn-only gates, missing regression suite | Phase 4 |
| **Tracing as direct infrastructure import** | 7 application modules break layer contract | import-linter output |

## Expected behavior contract (target)

### Market data

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| MD-1 | Subscription states: `requested→connecting→active→degraded→failed→stopped` | Partial — health on Dhan feed only |
| MD-2 | Freshness deadline; stale = `degraded`, not silent last value | Partial — Dhan stale reconnect |
| MD-3 | Normalized `QuoteReceived`/`DepthUpdated` on EventBus for **all** brokers | **Violated** — Upstox |
| MD-4 | Drop policy must increment metric **and** emit `SubscriptionDegraded` | **Violated** — counter only |
| MD-5 | Mapping failure = loud error, not fallback ID as symbol | **Violated** — security_id fallback |

### Order management

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| OM-1 | `PlaceOrder` returns `ACCEPTED`, `REJECTED`, or `UNKNOWN` synchronously | ✅ `OrderLifecycle` |
| OM-2 | UNKNOWN never mapped to success/reject without reconciliation | ✅ idempotency guard |
| OM-3 | Record-then-submit durable intent before broker I/O | ✅ `record_intent` |
| OM-4 | Idempotency on `correlation_id` + broker client order id | Partial |
| OM-5 | Placement gate until reconciliation ready | ✅ `TradingContext` |
| OM-6 | Single process-wide OMS book | Partial — singleton exists, multi-root undermines |

### Fills and portfolio

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| FP-1 | Fill idempotency on execution/trade ID | ✅ `ProcessedTradeRepository` |
| FP-2 | No double-application of fills to position | ✅ `TRADE_APPLIED` path |
| FP-3 | Position/PnL from execution ledger projection | Partial — dual book |
| FP-4 | Trade-before-order buffer with DLQ/alert on overflow | **Violated** — buffer then drop |

### Reconciliation

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| RC-1 | Compare fills, avg price, multiplier, realized PnL | **Violated** — status/qty |
| RC-2 | `ReconciliationDriftDetected` event on any material drift | Partial — logged |
| RC-3 | UNKNOWN orders trigger expedited reconcile | Partial |
| RC-4 | Repair requires explicit policy + operator audit trail | Partial — `auto_repair` gated |
| RC-5 | Trading re-enable only after drift-free reconcile | ✅ placement gate |

### Mode parity

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| MP-1 | Same command handlers for live/paper/replay/backtest | Partial |
| MP-2 | Mode differences only at clock, market source, execution transport | **Violated** — `PURE_SIM` |
| MP-3 | Parity gate cannot be skipped in production | **Violated** — `SKIP_PARITY_GATE` |
| MP-4 | Paper certification ≠ live certification | Documented, not enforced in CI |

### Operations

| Clause | Required behavior | Current enforcement |
|--------|-------------------|---------------------|
| OP-1 | CI green = all blocking gates passed (no warn-only for safety) | **Violated** |
| OP-2 | Certification artifacts linked to release | Partial |
| OP-3 | Kill switch blocks new orders; cancel open on shutdown | ✅ `TradingContext.shutdown` |
| OP-4 | Readiness proves bus, ledger, broker session, recon, clock | Partial |

## Silent failure simulation matrix

| Scenario | Expected | Observed | Loud/Silent |
|----------|----------|----------|-------------|
| Delayed/stale ticks | Degraded subscription | Dhan: reconnect; Upstox: listener only | Partial |
| WS disconnect | Reconnect + backfill | Dhan yes; Upstox re-subscribe | Loud |
| Partial fill | Cumulative qty update | ✅ order stream parsing | Loud |
| Ambiguous submit timeout | UNKNOWN + block retry | ✅ | Loud |
| Token expiry | Refresh + WS update | ✅ schedulers | Loud |
| Process restart | Recover from ledger + recon | Partial — sqlite + recon | Partial |
| Duplicate consumer | Idempotent fill reduce | ✅ trade_id cache | Loud |
| Broker API error on read | Error, not empty | **Often empty** — datalake/provider | **Silent** |
| `event_bus=None` | Fail closed | No-op publish | **Silent** |
| Upstox tick path | EventBus TICK | Listeners only | **Silent** to bus consumers |

## Ranked findings

### A — Production blockers

| ID | Finding | Confidence | Blast radius | Silent? |
|----|---------|------------|--------------|---------|
| A-01 | CI lint/certification paths broken — green does not mean tested | High | Release | Loud in logs, silent to operators |
| A-02 | Upstox market data does not publish to EventBus | High | Strategies, orchestrator, API WS | **Silent** |
| A-03 | Domain imports concrete brokers (`segment_mapper_for`) | High | Extensibility, import-linter | Loud at CI if lint ran |
| A-04 | No single authoritative fill→portfolio spine across all modes | High | Capital, research validity | Partial |
| A-05 | Reconciliation compares shallow fields; Upstox duplicates logic | High | PnL drift | **Silent** |
| A-06 | `parity_gate` replay invocation broken + skippable | High | Production boot | Silent with `SKIP_PARITY_GATE` |
| A-07 | SQLite OMS single-writer; multi-process not enforced | Medium | Deployment | **Silent** corruption |

### B — Delivery blockers

| ID | Finding | Confidence | Blast radius | Silent? |
|----|---------|------------|--------------|---------|
| B-01 | 3/15 import-linter contracts broken | High | Architecture regression | Loud |
| B-02 | Application imports `infrastructure.observability.tracing` directly | High | Layering | Loud |
| B-03 | `test_regression_suite.py` missing — Dhan regression workflow dead | High | Dhan releases | Loud |
| B-04 | 6+ composition roots — `process_context` warn-only on duplicate | High | Order state | Loud (warning) |
| B-05 | Pre-commit and mutation workflows reference stale paths | High | Developer feedback | Loud |
| B-06 | MyPy/Bandit/Safety/Doctor warn-only or continue-on-error | High | Security/types | Silent |
| B-07 | HTTP retry on ambiguous order writes (Dhan/Upstox) | Medium | Duplicate orders | Loud if duplicate occurs |

### C — Continuous improvement

| ID | Finding | Confidence | Blast radius | Silent? |
|----|---------|------------|--------------|---------|
| C-01 | 30+ stale `ignore_imports` in pyproject.toml | High | Lint accuracy | Silent |
| C-02 | `component` marker duplicated in pyproject.toml | High | Docs | Silent |
| C-03 | Duplicate mutation nightly workflows (02:00 UTC) | Medium | CI cost | Loud |
| C-04 | Synchronous event bus on hot path | Medium | Latency | Loud (slow) |
| C-05 | API WS drop-oldest without resync protocol | Medium | UI staleness | **Silent** |
| C-06 | Scanner correlation id gaps for OMS idempotency | Medium | Duplicate signals | Partial |