# TradeXV2 — Python Trading Framework

[![CI](https://github.com/Ganesh-Kusundal/trade_xv2/actions/workflows/ci.yml/badge.svg)](https://github.com/Ganesh-Kusundal/trade_xv2/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/Ganesh-Kusundal/trade_xv2/branch/main/graph/badge.svg)](https://codecov.io/gh/Ganesh-Kusundal/trade_xv2)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A Python-based, broker-agnostic algorithmic trading framework for Indian
exchanges (NSE, BSE, MCX), with DhanHQ and Upstox broker adapters, a
Rich/Textual CLI/TUI diagnostic terminal, and a complete OMS / event bus
/ risk / portfolio / strategy / backtesting / replay stack.

## Production-Ready Highlights (2026-06-15)

After the production certification remediation:

- **Central OMS on the live CLI path** (`B7`). Every `place_order` is
  risk-checked by the canonical `RiskManager`. The kill switch blocks
  orders deterministically. The `DailyPnlResetScheduler` clears the
  running PnL at IST 00:00.
- **Dhan CircuitBreaker split into 3 categories** (`A1`). Read failures
  no longer block order placement. Each category has its own threshold.
- **Thread-safe `RiskManager` with `RLock`** (`A2+A3`). Every
  mutator and reader is atomic; kill-switch flips mid-check cannot
  produce a torn read.
- **LifecycleManager owns every background service** (`A5+B5`).
  `close()` drains the `TokenRefreshScheduler`, the
  `ReconciliationService`, the `DailyPnlResetScheduler`, and the 3
  Dhan WebSocket threads. No more leaked daemon threads.
- **HTTP observability surface** (`B8+B9`). Production
  `BrokerService` exposes:
  - `GET /healthz` — liveness probe (200 if process is up)
  - `GET /readyz` — readiness probe (503 if any service is FAILED/UNHEALTHY)
  - `GET /metrics` — Prometheus text format including OMS risk
    state (`daily_pnl`, `kill_switch_active`, …)
- **Chaos test suite** (`B10`). 10 deterministic failure-mode tests
  covering token expiry, idempotency under concurrency, kill-switch
  flips, lifecycle drain under load, etc.
- **Dead-code elimination** (`C.4+C.5+C.6`). 9 deprecated modules
  deleted (~1,800 LOC). The canonical `domain.py` is the single
  source of truth for all types.
- **Real capital sizing** (`C.1`). The OMS `RiskManager` is sized
  to `gateway.funds().available_balance`, not a placeholder.

> **Onboarding** — see [`agent.md`](./agent.md) for the full module-by-module
> guide.

---

## Repository layout

```text
brokers/                    # Core broker module
  common/                   # Broker-agnostic abstractions
    core/                   # Canonical domain types (domain.py is the
                            # single source of truth — no more models.py
                            # or enums.py duplicates)
    lifecycle/              # LifecycleManager + ManagedService protocol
    observability/          # EventMetrics + HttpObservabilityServer
    oms/                     # OrderManager, PositionManager, RiskManager,
                            # DailyPnlResetScheduler, TradingContext
    resilience/              # Rate limiter, circuit breaker, retry
    event_bus.py             # Lock-safe pub/sub + dead-letter queue
  dhan/                     # DhanHQ broker adapter
    websocket.py            # DhanMarketFeed, DhanOrderStream,
                            # PollingMarketFeed — all ManagedService
  upstox/                   # Upstox broker adapter
  paper/                    # Paper-trading adapter

cli/                        # CLI/TUI diagnostic terminal
  services/broker_service.py  # Owns the LifecycleManager, HTTP server,
                              # OMS, broker gateway — production wire-up
  commands/                 # broker, account, portfolio, oms, market, ...
  main.py                   # Entry point
  tests/                    # test_commands, test_broker_service_lifecycle,
                            # test_b7_oms_wireup, test_http_observability_wireup

tests/chaos/                # Deterministic failure-mode tests (B10)
analytics/                  # Research + backtest + scanner + replay
datalake/                   # Read-only gateway + TradeJournal (WAL SQLite)

scripts/verify_event_replay.py  # Replay-determinism CI check (Phase 1 cert)
```

---

## Development setup

### Prerequisites

- Python 3.10+
- Git

### Installation

```bash
git clone https://github.com/Ganesh-Kusundal/trade_xv2.git
cd trade_xv2

# The project ships a working virtualenv at venv/ (Python 3.13,
# miniconda-based) that already has all runtime + dev dependencies
# installed. The ./tradex launcher uses it directly.
source venv/bin/activate

# Or, create a fresh venv from scratch:
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

> The `./tradex` launcher hardcodes `venv/bin/python`. The on-disk
> `.venv/` (created later with `uv`) is a symlink to miniconda and
> does **not** ship `pip` or the full dep set — use `venv/` for
> running CLI smoke tests until the conda env is rebuilt.

### Running tests

```bash
# Quick: unit + contract + chaos tests only (~30 seconds)
pytest -m "not integration and not sandbox and not live_readonly" -q

# Full: includes integration tests (requires Dhan credentials)
pytest -q

# With coverage (HTML + XML)
pytest --cov=brokers --cov=cli --cov=datalake --cov=tests/chaos \
      --cov-branch --cov-report=term-missing --cov-report=html

# CLI endpoint matrix (offline + T1 smoke)
pytest cli/tests/test_cli_endpoint_matrix.py -m cli_endpoint -q

# Replay determinism verifier (Phase 1 cert)
python -m scripts.verify_event_replay
```

### Code quality

```bash
ruff check .
ruff format --check .
mypy brokers/ cli/ datalake/
```

---

## CLI usage

```bash
./tradex                # TUI dashboard
./tradex quote RELIANCE # one-shot quote lookup
./tradex orders          # today's orders
./tradex positions       # current positions
./tradex holdings        # holdings
./tradex oms             # OMS diagnostics
./tradex doctor         # connectivity check
```

When the CLI is running, it also exposes HTTP observability on
`http://127.0.0.1:8765/`:
- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /metrics` — Prometheus text format

---

## Broker adapter status

### Dhan (`brokers/dhan/`)

Complete. Implements the `MarketDataGateway` ABC and exposes the
Dhan v2 REST + WebSocket APIs. The 3 WebSocket services
(`DhanMarketFeed`, `DhanOrderStream`, `PollingMarketFeed`) are
all `ManagedService` instances — registered with the broker's
`LifecycleManager` and drained on `close()`.

### Upstox (`brokers/upstox/`)

Complete. `UpstoxBroker` extends the `BrokerConnection` ABC
(capability-based service discovery) and wires every adapter
(market data v2/v3, orders, portfolio, kill switch, alerts,
margin, GTT, cover, slice, etc.).

### Paper (`brokers/paper/`)

Complete. In-process simulator with `RLock`-protected in-memory
state.

---

## Safety notes

- Order placement is validated before REST submission. Validation
  errors block placement. The OMS `RiskManager` enforces the
  kill switch, position_pct, gross_exposure_pct, and daily_loss_pct
  gates.
- Do **not** run live orders unless you understand the strategy,
  broker limits, and exchange rules.
- `.env.local` with real credentials must never be committed.
- Live / sandbox tests should only run with explicit user approval
  and safe credentials.

---

## Verification

Static checks and module-owned suites:

```bash
ruff check .
ruff format --check .
mypy brokers/ cli/ datalake/
```

Test suites:

```bash
pytest -m unit
pytest -m contract
pytest tests/chaos/              # B10 chaos tests
pytest tests/integration/       # OMS event-replay determinism
```

Standalone diagnostics:

```bash
python scripts/debug/broker_load_check.py
python check_dhan.py
```

---

## Architecture

The architecture mirrors the Java sibling project `Trade_J`:

| Java (`Trade_J`) | Python (`Trade_XV2`) |
|---|---|
| `IBrokerConnection` + `Capability` enum | `brokers.common.gateway.MarketDataGateway` ABC |
| Token-bucket rate limiter | `brokers.common.resilience.rate_limiter.TokenBucketRateLimiter` |
| Circuit breaker | `brokers.common.resilience.circuit_breaker.CircuitBreaker` |
| Retry with exponential backoff | `brokers.common.resilience.retry.RetryExecutor` |
| `GatewayResult` monad | `brokers.common.core.result.GatewayResult` |
| SPI ports | `brokers.common.api.ports.*` |
| Broker router + fallback | `brokers.common.intelligent_gateway.IntelligentGateway` |

### Deep module map (2026-06)

| Layer | Module | Role |
|---|---|---|
| Exchange resolution | `brokers/common/core/exchange_segments.py` | Canonical `parse_segment()` |
| Dhan wire/SDK | `brokers/dhan/segments.py` | `to_dhan_wire()`, `to_sdk_int()` |
| OMS facade | `brokers/common/oms/order_manager.py` | Single order orchestration entry |
| OMS internals | `brokers/common/oms/_internal/` | Validators, audit, risk (private) |
| Execution transport | `brokers/common/execution/gateway_submit.py` | OMS `submit_fn` factory |
| Upstox capabilities | `brokers/upstox/capabilities/` | Grouped adapter clusters |
| Data lake store | `datalake/store/parquet_store.py` | Parquet load/resample (deep) |
| CLI composition | `cli/services/composition.py` | `build_cli_runtime()` |
| Batch utility | `brokers/common/batch_executor.py` | Shared parallel fetch |

See ADR-006 (exchange resolution) and ADR-007 (OMS-first execution) in `docs/adr/`.

The Python translation uses `@dataclass(slots=True, frozen=True)` for
domain types, `threading.RLock` for concurrency, and `pydantic` only
at adapter boundaries (now eliminated in favor of dataclasses).
