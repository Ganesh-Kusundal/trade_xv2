# Developer Quickstart

Get up and running with TradeXV2 in under 5 minutes. No live broker credentials required — everything uses the built-in paper broker.

---

## 1. Installation

**End-user (pip from PyPI):**

```bash
pip install tradexv2
```

**Development (editable with dev tools):**

```bash
git clone https://github.com/your-org/Trade_XV2.git
cd Trade_XV2
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

**Optional extras:**

```bash
pip install -e ".[mcp]"    # MCP tool server for LLM agents
pip install -e ".[agent]"  # Anthropic agent integration
```

---

## 2. Configuration

The paper broker works out of the box with zero configuration. For real brokers, create `.env.local` in the repo root:

```bash
# .env.local — paper broker (default, no credentials needed)
# No configuration required for paper mode.

# For Dhan (live/sandbox):
# DHAN_CLIENT_ID=your_client_id
# DHAN_ACCESS_TOKEN=your_access_token

# For Upstox (live/sandbox):
# UPSTOX_ACCESS_TOKEN=your_access_token
```

Paper broker mode is `"sim"` by default — it simulates order execution locally without hitting any exchange.

---

## 3. First Quote (3 lines)

```python
import tradex

session = tradex.connect("paper")
stock = session.universe.equity("RELIANCE")
stock.refresh()
print(f"RELIANCE LTP: {stock.ltp}")
session.close()
```

That's it. The `connect("paper")` call creates a session with simulated market data. You can also use `session.stock("RELIANCE")` as a shorthand.

---

## 4. First Trade

```python
from decimal import Decimal
import tradex

session = tradex.connect("paper")

# Place a limit order
stock = session.universe.equity("RELIANCE")
result = stock.buy(
    1,
    price=Decimal("2500"),
    correlation_id="quickstart:buy:1",
)
print(f"Order success: {result.success}")
print(f"Order ID: {result.order.order_id if result.order else result.error}")

# Or use the session-level API:
result2 = session.sell(stock, 1, price=Decimal("2501"))
print(f"Sell success: {result2.success}")

# Check positions
account = session.account
account.refresh()
print(f"Positions: {account.positions}")
print(f"Funds: {account.funds}")

session.close()
```

**Available order methods:**

| Method | Description |
|--------|-------------|
| `stock.buy(qty, price=...)` | Buy with optional limit price |
| `session.sell(stock, qty, price=...)` | Sell via session |

---

## 5. Run Certification

Validate that your broker connection passes all certification checks:

```bash
# Paper broker (always passes — good for CI baseline)
broker certify --broker paper

# Live broker (requires credentials in .env.local)
broker certify --broker dhan

# JSON output (for CI pipelines)
broker certify --broker paper --json
```

You can also run a quick startup self-test (faster than full certification):

```bash
broker verify --broker paper
```

---

## 6. CLI Exploration

The `broker` CLI provides 30+ commands. Here's a walkthrough:

```bash
# Discover registered brokers
broker discover

# Connect and check status
broker connect --broker paper

# Get a quote
broker quote RELIANCE

# Fetch historical data
broker history RELIANCE --tf 1D --days 5

# Check portfolio
broker positions
broker holdings
broker funds

# Place and manage orders
broker order RELIANCE 1 --side BUY --price 2500 --order-type LIMIT
broker orders
broker cancel <order_id>
broker modify <order_id> --quantity 2

# Market data
broker depth RELIANCE
broker option_chain NIFTY

# Symbol resolution
broker symbols RELIANCE
broker instrument RELIANCE --exchange NSE

# Diagnostics
broker doctor           # Full environment pre-flight
broker health           # Health checks
broker diagnose         # Connectivity, auth, data, orders
broker benchmark        # Latency/throughput benchmark
broker market_hours     # Current IST market phase
broker mappings         # Symbol mapping round-trip validation

# Interactive shell (menu-driven REPL)
broker shell
```

**Global options:**

```
--broker TEXT     Broker id: paper, dhan, upstox (default: paper)
--json            Emit raw JSON instead of Rich tables
```

### Unified `tradex` CLI

```bash
tradex broker quote RELIANCE    # Delegates to broker CLI
tradex version                  # Print installed version
tradex ui                       # Launch rich terminal UI
```

---

## 7. Next Steps

| Topic | Location |
|-------|----------|
| **SDK Reference** | [`docs/sdk/`](sdk/) — Python API documentation |
| **CLI Reference** | [`docs/cli/`](cli/) — All `broker` commands |
| **MCP Tool Reference** | [`docs/mcp/`](mcp/) — LLM agent tool definitions |
| **Broker Certification** | [`docs/broker_certification.md`](broker_certification.md) — Full certification suite |
| **Golden Datasets** | [`tests/fixtures/golden/README.md`](../tests/fixtures/golden/README.md) — Test data format |
| **Examples** | [`examples/`](../examples/) — Working demo scripts |
| **Object Model** | [`examples/object_model_quickstart.py`](../examples/object_model_quickstart.py) — Product API walkthrough |
| **Architecture** | [`docs/architecture/`](architecture/) — System design docs |
| **Transformation Roadmap** | [`docs/TRANSFORMATION_ROADMAP.md`](TRANSFORMATION_ROADMAP.md) — Full project plan |

### Connect to a live broker

1. Add credentials to `.env.local` (see [Configuration](#2-configuration))
2. Run `broker connect --broker dhan` to verify authentication
3. Run `broker certify --broker dhan --live` to validate the full live suite
4. Switch your Python script from `tradex.connect("paper")` to `tradex.connect("dhan", mode="trade")`

### MCP Integration

```bash
# Start the MCP server (stdio transport for LLM agents)
broker-mcp
```

This exposes `broker_connect`, `broker_quote`, `broker_history`, `broker_certify`, and 20+ other tools via the Model Context Protocol.

---

*Generated for Phase 4 — Task D4.7 of the Transformation Roadmap.*
