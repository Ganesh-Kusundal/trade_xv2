# TradeXV2 — Python Trading Framework

[![CI](https://github.com/YOUR_ORG/Trade_XV2/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_ORG/Trade_XV2/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/YOUR_ORG/Trade_XV2/branch/main/graph/badge.svg)](https://codecov.io/gh/YOUR_ORG/Trade_XV2)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A Python-based, broker-agnostic algorithmic trading framework for Indian
exchanges (NSE, BSE, MCX), with a DhanHQ adapter, a Rich/Textual CLI/TUI
diagnostic terminal, and resilience, OMS, event-bus, portfolio, risk,
strategy, backtesting, and replay modules.

The architecture mirrors a Java sibling project (`Trade_J`) — capability-based
broker connections, SPI ports, token-bucket rate limiting, circuit breakers,
retry with exponential backoff, a `GatewayResult` monad, and broker routing
with fallback — translated into idiomatic Python (dataclasses, ABCs,
`pydantic` v2 where validation matters).

> **Onboarding** — see [`agent.md`](./agent.md) for the full module-by-module
> guide, conventions, and "how to" recipes.

---

## Repository layout

```text
brokers/                    # Core broker module
  common/                   # Broker-agnostic abstractions
    api/                    # SPI ports & provider registry
      ports.py              # Abstract capability contracts
      spi.py                # BrokerSource / BrokerDescriptor / BrokerProvider
    contracts/              # Contract test suites
      broker_contract.py    # BrokerContractSuite (parameterized contract tests)
      module_test_suite.py  # ModuleTestSuite runner
    core/                   # Domain types & shared plumbing
      auth.py               # TokenSource, AuthManager, TOTP, token state store
      broker.py             # Broker ABC (canonical adapter interface)
      connection.py         # BrokerConnection ABC, Capability, ConnectionStatus
      domain.py             # Canonical dataclasses (Order, Position, Holding, ...)
      enums.py              # ExchangeSegment, OrderType, ProductType, ...
      instruments.py        # Instrument / InstrumentRegistry
      models.py             # Pydantic models (legacy facade surface)
      result.py             # GatewayResult monad
      schemas.py            # DataFrame schemas + builders + validation
    resilience/             # Rate limiter, circuit breaker, retry, backoff
  dhan/                     # DhanHQ broker adapter
    auth/                   # Auth client, config, context, HTTP, URL resolver
    mapper/                 # Dhan ↔ canonical mapping
    market_data/            # Quotes, history, options, portfolio, margin
    orders/                 # Order cmd/query, validator, BO/CO/GTT/slice, futures
    websocket/              # Market-feed and order-stream WebSockets
    broker.py               # DhanBroker facade
    client.py               # DhanClientHolder, TokenRotationListener
    exceptions.py           # DhanApiError
  paper/                    # Paper-trading adapter (in-progress)
  gateway.py                # Gateway — high-level fluent facade
  handle.py                 # BrokerHandle — per-broker fluent wrapper
  router.py                 # BrokerRouter — multi-broker routing + fallback
  multiplexer.py            # WebSocket subscription fan-out

cli/                        # CLI/TUI diagnostic terminal
  commands/                 # broker, account, portfolio, oms, market, ...
  services/                 # BrokerService, OmsService, EventBusService
  views/                    # Textual TUI app
  main.py                   # Entry point

oms/  event_bus/  portfolio/  risk/  strategy/  backtesting/  replay/
                            # Placeholder modules (see agent.md §12)

tests/                      # Top-level test suites
  e2e/                      # End-to-end
  regression/               # Regression (placeholder)
  performance/              # Performance (placeholder)

scripts/debug/              # Ad-hoc debug scripts (not collected by pytest)

check_dhan.py               # Standalone Dhan connectivity diagnostic
tradex                      # CLI entry point (bash → venv python -m cli.main)
```

The legacy single-package alias `broker/` (singular) still exists at the repo
root and re-exports the modern `brokers/` package, so the spec-style
`from broker import Gateway` continues to work. New code should import from
`brokers.*`.

> **Deprecation notice** — the singular `broker/` alias is deprecated and will
> be removed in Phase 2. Please migrate imports to `brokers.*` at your
> earliest convenience.

---

## Development setup

### Prerequisites

- Python 3.10+
- Git
- Make (optional)

### Installation

```bash
# Clone and install
git clone https://github.com/YOUR_ORG/Trade_XV2.git
cd Trade_XV2
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running tests

```bash
# Quick: unit + contract tests only (~30 seconds)
pytest -m "not integration and not sandbox and not live_readonly" -q

# Full: includes integration tests
pytest -q

# With coverage
pytest --cov=brokers --cov-branch --cov-report=term-missing

# Specific broker
pytest brokers/dhan/tests/ -v
pytest brokers/upstox/tests/ -v
```

### Code quality

```bash
# Lint and format
ruff check .
ruff format .

# Type check
mypy brokers/

# All-in-one
make lint test  # if Makefile exists
```

### Test markers

| Marker | Purpose | Requires credentials? |
|---|---|---|
| `unit` | Module-owned unit tests | No |
| `contract` | Broker contract tests | No |
| `integration` | External API tests | Sometimes |
| `sandbox` | Order placement/cancellation tests | Yes (Dhan sandbox) |
| `live_readonly` | Live read-only tests | Yes (Dhan live) |
| `performance` | Latency benchmarks | No |
| `stress` | Long-running concurrency tests | No |

---

## Public import surface

```python
from brokers.dhan import DhanBroker
from brokers.common.core.enums import (
    ExchangeSegment, ProductType, TransactionType, OrderType,
)
from brokers.common.core.models import OrderRequest
```

Or via the legacy alias:

```python
from broker import Gateway

g = Gateway()
g.ltp("TCS")
```

---

## Dhan configuration

Copy `.env.example` to `.env.local` and fill only local values. Do **not**
commit secrets.

```bash
cp .env.example .env.local
```

Supported settings:

```text
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
DHAN_AUTH_MODE=STATIC
DHAN_ENVIRONMENT=LIVE
DHAN_REST_BASE_URL=
DHAN_PIN=
DHAN_TOTP_SECRET=
DHAN_PIN_FILE=config/dhan-pin.txt
DHAN_TOTP_SECRET_FILE=config/dhan-totp-secret.txt
DHAN_TOKEN_STATE_FILE=runtime/dhan-token-state.json
DHAN_REFRESH_BUFFER_MINUTES=10
```

`DHAN_AUTH_MODE` accepts:

- `STATIC` — use a preconfigured access token.
- `TOTP_GENERATED` — generate/renew via Dhan PIN + TOTP secret.
- `WEB_RENEWABLE` — adopt a bootstrap token and renew when needed.

---

## Quick start

```python
from brokers.dhan import DhanBroker
from brokers.common.core.enums import ExchangeSegment, ProductType, TransactionType, OrderType
from brokers.common.core.models import OrderRequest

broker = DhanBroker.from_env()
broker.connect()

quote = broker.get_market_quote_rest("2885", ExchangeSegment.NSE)

order = OrderRequest(
    security_id="2885",
    exchange_segment=ExchangeSegment.NSE,
    transaction_type=TransactionType.BUY,
    quantity=10,
    price=2500,
    order_type=OrderType.LIMIT,
    product_type=ProductType.CNC,
)
preview = broker.preview_order(order)
response = broker.place_order_rest(order)
```

Launch the diagnostic terminal:

```bash
./tradex                # TUI dashboard
./tradex quote RELIANCE # one-shot CLI command
./tradex doctor         # connectivity checks
```

---

## Dhan adapter status

**Adopted / implemented** (see `brokers/dhan/`):

- `DhanBroker` facade implementing `BrokerConnection` with capability registration.
- Auth client + token manager, token persistence, TOTP generation, renewal,
  and bootstrap-token adoption (`brokers/dhan/auth/`).
- Authenticated REST HTTP client and Dhan v2 URL resolver.
- Instrument catalog resolver backed by the Dhan master CSV.
- REST clients for orders, trades, quotes, historical candles, option chain
  and expiries, portfolio, holdings, funds, ledger, profile, and the
  margin calculator.
- Order preview/validation with lot-size, product/segment, and notional
  checks.
- Special-order adapters: bracket, cover, GTT, slice, futures, conditional
  alerts, session risk.
- Resilience: token-bucket rate limiter, circuit breaker, exponential
  backoff with jitter, retry executor.
- Capability-based broker connection pattern (mirrors `Trade_J`'s
  `IBrokerConnection`).
- Adapter package (`brokers/dhan/adapters/`) and mapper layer
  (`brokers/dhan/mapper/`) mirroring the Java layout.
- WebSocket market-feed and order-stream scaffolding (parsers in progress).

**Pending / incomplete** (relative to `Trade_J/broker/dhan`):

- WebSocket parser completion and reconnect controller / health monitor.
- 20-level market-depth parser/provider (provider scaffolded, parser pending).
- Idempotency cache for duplicate order placement safety.
- News provider.
- Full SPI service-loader equivalent to Java `META-INF/services`.
- Adapters for Upstox and ICICI (skeletons under `brokers/`).

---

## Safety notes

- Order placement is validated before REST submission. Validation errors
  block placement; high-notional orders produce warnings unless strict
  validation is added later.
- Do **not** run live orders unless you understand the strategy, broker
  limits, and exchange rules.
- `.env.local` with real credentials must never be committed.
- Sandbox/live tests should only run with explicit user approval and safe
  credentials.

---

## Verification

Static checks and module-owned suites:

```bash
python -m compileall brokers cli tests scripts
python -m brokers.dhan.tests.run
python -m brokers.common.core.tests.run
python -m brokers.common.resilience.tests.run
python -m brokers.common.api.tests.run
pytest -m unit
pytest -m contract
```

Integration / live / performance:

```bash
pytest tests/e2e
pytest -m "integration or sandbox or live_readonly"   # credentials required
pytest tests/performance
```

Standalone diagnostics:

```bash
python check_dhan.py            # Dhan connectivity walk-through
python scripts/debug/broker_load_check.py
```
