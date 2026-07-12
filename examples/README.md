# Sample Applications — Phase 4 D4.6

> **Purpose:** 4 end-to-end sample applications demonstrating real-world TradeXV2
> usage patterns. Each app is a standalone directory with its own `main.py`,
> configuration, and README. All apps run against the **paper broker** by default.

---

## Existing Examples

These files already exist in `examples/` and cover low-level SDK usage:

| File | Description |
|------|-------------|
| `minimal_session/run.py` | Connect → quote → disconnect (20 lines) |
| `broker_usage_demo.py` | Full broker API tour: equity, index, futures, MCX, depth, streaming, account |
| `live_connection_test.py` | Multi-broker connectivity test (paper, Dhan, Upstox) |
| `live_data_flow_test.py` | Live data flow validation with real broker |
| `object_model_quickstart.py` | Product API demo — `tradex.connect()` without gateway imports |

The 4 new sample applications build on these patterns and add production-grade
scenarios: scanning, live dashboards, backtesting, and multi-broker monitoring.

---

## App 1: Market Scanner

> Scan the NSE universe, score candidates, and place paper orders on top picks.

**Directory:** `examples/market_scanner/`

### Directory Structure

```
examples/market_scanner/
├── README.md          # App-specific docs
├── main.py            # Entry point
├── config.yaml        # Scanner + order parameters
├── scanner.py         # Scanner configuration and execution
├── order_placer.py    # Paper order placement logic
└── reporter.py        # Results formatting and display
```

### Main Entry Point: `main.py`

```python
#!/usr/bin/env python3
"""Market Scanner — scan NSE universe, score, and place paper orders.

Usage:
    cd examples/market_scanner
    python main.py
    python main.py --config custom.yaml
"""

from __future__ import annotations

import argparse
import tradex
from decimal import Decimal

from scanner import run_scanner
from order_placer import place_orders
from reporter import print_candidates, print_order_summary


def main(config_path: str = "config.yaml") -> None:
    # 1. Connect to paper broker
    session = tradex.connect("paper")
    print(f"Connected: {session.describe()}")

    try:
        # 2. Run scanner on NSE universe
        candidates = run_scanner(session, config_path)

        # 3. Display candidates with scores
        print_candidates(candidates)

        # 4. Place paper orders on top N candidates
        orders = place_orders(session, candidates, max_positions=5)
        print_order_summary(orders)

    finally:
        session.close()
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    main(args.config)
```

### Configuration: `config.yaml`

```yaml
scanner:
  # Momentum scanner parameters
  universe: "nse500"
  timeframe: "1D"
  lookback_days: 30
  min_volume: 100000
  min_score: 60.0
  top_n: 10

  # Scoring weights
  weights:
    momentum_5d: 0.25
    momentum_20d: 0.25
    volume_surge: 0.20
    rsi_position: 0.15
    trend_alignment: 0.15

order:
  # Paper order parameters
  order_type: "LIMIT"
  quantity: 1
  max_positions: 5
  price_buffer_pct: 0.5   # Limit price offset from LTP
```

### Scanner Module: `scanner.py`

```python
"""Scanner execution — runs MomentumScanner against the universe."""

from __future__ import annotations
from analytics.scanner.rules.engine import RuleEngine
from analytics.scanner.scanners import MomentumScanner


def run_scanner(session, config_path: str) -> list[dict]:
    """Run the scanner and return ranked candidates."""
    # Load config
    # Initialize scanner with parameters from config
    # Build universe DataFrame from session
    # Execute scan → ScanResult
    # Return top N candidates as list of dicts
    ...
```

### Expected Output

```
Connected: paper (session-id=abc123)
Running scanner on NSE500 universe...

Top 10 Candidates:
  #1  RELIANCE  score=87.3  reason="Strong momentum + volume surge"
  #2  INFY      score=82.1  reason="Breakout above SMA-50"
  #3  HDFCBANK  score=79.8  reason="Bullish RSI crossover"
  #4  TCS       score=76.4  reason="Volume 2.3x average"
  #5  ITC       score=74.2  reason="Trend alignment + low RSI"
  ... (5 more)

Placing paper orders:
  ✅ BUY RELIANCE  qty=1  limit=2499.75  (score=87.3)
  ✅ BUY INFY      qty=1  limit=1573.25  (score=82.1)
  ✅ BUY HDFCBANK  qty=1  limit=1662.50  (score=79.8)
  ✅ BUY TCS       qty=1  limit=3859.20  (score=76.4)
  ✅ BUY ITC       qty=1  limit=467.50   (score=74.2)

Orders placed: 5/5  (paper mode — no real execution)
Done.
```

### Configuration Requirements

| Config Key | Required | Default | Notes |
|------------|----------|---------|-------|
| `scanner.universe` | Yes | `nse500` | NSE universe code |
| `scanner.timeframe` | No | `1D` | Bar timeframe |
| `scanner.min_score` | No | `60.0` | Minimum score threshold |
| `scanner.top_n` | No | `10` | Max candidates to display |
| `order.max_positions` | No | `5` | Max paper orders to place |
| `order.price_buffer_pct` | No | `0.5` | % offset from LTP for limit |

---

## App 2: Real-Time Dashboard

> WebSocket streaming with real-time quotes, order book depth, and position P&L.

**Directory:** `examples/realtime_dashboard/`

### Directory Structure

```
examples/realtime_dashboard/
├── README.md          # App-specific docs
├── main.py            # Entry point (text-based dashboard)
├── config.yaml        # Watchlist + refresh settings
├── stream_handler.py  # WebSocket subscription and callback
├── depth_display.py   # Order book depth rendering
└── pnl_tracker.py     # Position P&L computation
```

### Main Entry Point: `main.py`

```python
#!/usr/bin/env python3
"""Real-Time Dashboard — live quotes, depth, and P&L in the terminal.

Usage:
    cd examples/realtime_dashboard
    python main.py
    python main.py --symbols RELIANCE,INFY,TCS --duration 60
"""

from __future__ import annotations

import argparse
import time
import tradex

from stream_handler import subscribe_watchlist
from depth_display import render_depth
from pnl_tracker import compute_pnl


def main(symbols: list[str], duration_seconds: int = 30) -> None:
    session = tradex.connect("paper")
    print(f"Connected: {session.describe()}")

    try:
        instruments = []
        for sym in symbols:
            inst = session.universe.equity(sym)
            inst.refresh()
            instruments.append(inst)

        # Subscribe to live tick stream
        handles = subscribe_watchlist(instruments, on_tick=_on_tick)

        # Main loop — refresh display periodically
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            _render_dashboard(session, instruments)
            time.sleep(1.0)

        # Cleanup
        for h in handles:
            h.unsubscribe()

    finally:
        session.close()


def _on_tick(snapshot):
    """Called on each tick — updates internal state."""
    ...


def _render_dashboard(session, instruments):
    """Render terminal dashboard with latest quotes + depth + P&L."""
    ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="RELIANCE,INFY,TCS")
    parser.add_argument("--duration", type=int, default=30)
    args = parser.parse_args()
    main(args.symbols.split(","), args.duration)
```

### Configuration: `config.yaml`

```yaml
dashboard:
  watchlist:
    - RELIANCE
    - INFY
    - TCS
    - HDFCBANK
    - ITC
  refresh_interval_sec: 1
  show_depth: true
  depth_symbol: RELIANCE   # Show depth for this symbol
  show_pnl: true

stream:
  # Paper broker has limited streaming — this gracefully degrades
  mode: "poll"  # "ws" for live brokers, "poll" for paper
  poll_interval_ms: 500
```

### Expected Output

```
Connected: paper (session-id=abc123)
Dashboard running for 30s … Press Ctrl+C to stop

╔══════════════════════════════════════════════════════════╗
║ TradeXV2 Real-Time Dashboard                            ║
╠══════════════════════════════════════════════════════════╣
║ Symbol     LTP        Bid        Ask       Δ1m    Vol   ║
║ RELIANCE   2487.50    2487.00    2488.00   +0.12%  12.3K ║
║ INFY       1565.30    1565.00    1565.60   -0.05%   8.7K ║
║ TCS        3840.00    3839.50    3840.50   +0.08%   5.1K ║
╠══════════════════════════════════════════════════════════╣
║ Depth: RELIANCE                                         ║
║   Bids:  2487.00 (200)  2486.50 (350)  2486.00 (150)   ║
║   Asks:  2488.00 (180)  2488.50 (420)  2489.00 (275)   ║
╠══════════════════════════════════════════════════════════╣
║ Position P&L                                            ║
║   RELIANCE  qty=10  avg=2450  pnl=+375.00              ║
║   INFY      qty=5   avg=1580  pnl=-73.50               ║
║   Total unrealized: +₹301.50                            ║
╚══════════════════════════════════════════════════════════╝

[refreshes every 1s]
```

### Configuration Requirements

| Config Key | Required | Default | Notes |
|------------|----------|---------|-------|
| `dashboard.watchlist` | Yes | `[RELIANCE,INFY,TCS]` | Symbols to track |
| `dashboard.refresh_interval_sec` | No | `1` | Display refresh rate |
| `dashboard.show_depth` | No | `true` | Show order book depth |
| `dashboard.show_pnl` | No | `true` | Show position P&L |
| `stream.mode` | No | `poll` | `ws` for live, `poll` for paper |

---

## App 3: Backtest Runner

> Load historical data, configure a strategy, run a backtest, and generate a report.

**Directory:** `examples/backtest_runner/`

### Directory Structure

```
examples/backtest_runner/
├── README.md          # App-specific docs
├── main.py            # Entry point
├── config.yaml        # Strategy + backtest parameters
├── data_loader.py     # Load data from datalake or broker history
├── strategy.py        # Strategy definition (crossover, momentum, etc.)
├── runner.py          # BacktestEngine orchestration
└── reporter.py        # Performance report generation
```

### Main Entry Point: `main.py`

```python
#!/usr/bin/env python3
"""Backtest Runner — load data, configure strategy, run backtest, generate report.

Usage:
    cd examples/backtest_runner
    python main.py
    python main.py --symbol RELIANCE --years 5
    python main.py --config custom_strategy.yaml
"""

from __future__ import annotations

import argparse
import tradex

from data_loader import load_data
from strategy import build_strategy
from runner import run_backtest
from reporter import generate_report


def main(
    symbol: str = "RELIANCE",
    years: int = 2,
    config_path: str = "config.yaml",
) -> None:
    # 1. Load historical data
    df = load_data(symbol, years)
    print(f"Loaded {len(df)} bars for {symbol}")

    # 2. Build strategy pipeline
    strategy = build_strategy(config_path)
    print(f"Strategy: {strategy.name}")

    # 3. Run backtest
    result = run_backtest(df, strategy, config_path)

    # 4. Generate report
    generate_report(result, symbol, output_dir="reports/")
    print("Report saved to reports/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    main(args.symbol, args.years, args.config)
```

### Configuration: `config.yaml`

```yaml
backtest:
  # Data parameters
  symbol: "RELIANCE"
  timeframe: "1D"
  years: 2

  # Capital
  initial_capital: 1000000
  commission_pct: 0.03
  slippage_pct: 0.01

  # Strategy
  strategy: "ma_crossover"
  params:
    fast_period: 10
    slow_period: 50
    rsi_filter: true
    rsi_period: 14
    rsi_oversold: 30
    rsi_overbought: 70

  # Risk
  stop_loss_pct: 2.0
  take_profit_pct: 5.0
  max_position_pct: 20.0

  # Report
  output_dir: "reports/"
  format: "html"  # "text" or "html"
```

### Strategy Module: `strategy.py`

```python
"""Strategy definitions for the backtest runner."""

from __future__ import annotations
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline.features import SMA, RSI, ATR, ROC, Momentum, Trend
from analytics.strategy import StrategyPipeline


def build_strategy(config_path: str) -> StrategyPipeline:
    """Build strategy pipeline from config."""
    # Load config
    # Build FeaturePipeline with configured indicators
    # Build StrategyPipeline with crossover/momentum logic
    # Return StrategyPipeline ready for BacktestEngine
    ...
```

### Expected Output

```
Loaded 504 bars for RELIANCE (2024-07-12 → 2026-07-11)
Strategy: ma_crossover (fast=10, slow=50)

═══════════════════════════════════════════════
  BACKTEST REPORT: RELIANCE — MA Crossover
═══════════════════════════════════════════════
  Period:        2024-07-12 → 2026-07-11 (504 bars)
  Capital:       ₹10,00,000

  Performance:
    Total Return:    +14.32%
    Ann. Return:     +7.18%
    Sharpe Ratio:    1.87
    Sortino Ratio:   2.43
    Max Drawdown:    -8.21%

  Trading:
    Total Trades:    18
    Win Rate:        58.3%
    Profit Factor:   1.64
    Avg Win:         ₹12,450
    Avg Loss:        ₹-7,230

  Risk:
    Stop Loss:       2.0%
    Take Profit:     5.0%
    Max Position:    20%
═══════════════════════════════════════════════

Report saved to reports/RELIANCE_ma_crossover.html
```

### Configuration Requirements

| Config Key | Required | Default | Notes |
|------------|----------|---------|-------|
| `backtest.symbol` | Yes | `RELIANCE` | Target symbol |
| `backtest.years` | No | `2` | Historical data depth |
| `backtest.strategy` | Yes | `ma_crossover` | Strategy name |
| `backtest.params` | Yes | — | Strategy-specific parameters |
| `backtest.initial_capital` | No | `1000000` | Starting capital (₹) |
| `backtest.commission_pct` | No | `0.03` | Per-trade commission |
| `backtest.output_dir` | No | `reports/` | Report output path |

---

## App 4: Multi-Broker Monitor

> Connect to multiple brokers, compare prices in real time, and track arbitrage opportunities.

**Directory:** `examples/multi_broker_monitor/`

### Directory Structure

```
examples/multi_broker_monitor/
├── README.md          # App-specific docs
├── main.py            # Entry point
├── config.yaml        # Broker configs + alert thresholds
├── broker_connector.py  # Multi-broker session management
├── price_comparator.py  # Cross-broker price comparison
├── arbitrage_tracker.py  # Arbitrage opportunity detection
└── alert_manager.py    # Alert display and logging
```

### Main Entry Point: `main.py`

```python
#!/usr/bin/env python3
"""Multi-Broker Monitor — compare prices across brokers and track arbitrage.

Usage:
    cd examples/multi_broker_monitor
    python main.py
    python main.py --symbols RELIANCE,INFY --duration 120

Note: With paper broker only, all brokers return simulated data.
      For real comparison, configure live broker credentials in config.yaml.
"""

from __future__ import annotations

import argparse
import time
import tradex

from broker_connector import connect_brokers
from price_comparator import compare_prices
from arbitrage_tracker import detect_opportunities
from alert_manager import AlertManager


def main(symbols: list[str], duration_seconds: int = 60) -> None:
    # 1. Connect to configured brokers
    brokers = connect_brokers(symbols)
    print(f"Connected to {len(brokers)} broker(s)")

    alert_mgr = AlertManager()

    try:
        end_time = time.time() + duration_seconds
        while time.time() < end_time:
            # 2. Fetch quotes from each broker for each symbol
            quotes = _fetch_all_quotes(brokers, symbols)

            # 3. Compare prices across brokers
            comparisons = compare_prices(quotes)
            _display_comparisons(comparisons)

            # 4. Detect arbitrage opportunities
            opportunities = detect_opportunities(
                comparisons,
                min_spread_pct=0.1,  # Minimum spread to trigger alert
            )

            # 5. Alert on discrepancies
            for opp in opportunities:
                alert_mgr.alert(opp)

            time.sleep(5.0)  # Poll interval

    finally:
        for b in brokers:
            b.close()
        print("All broker connections closed.")


def _fetch_all_quotes(brokers, symbols):
    """Fetch latest quote from each broker for each symbol."""
    ...


def _display_comparisons(comparisons):
    """Display price comparison table."""
    ...


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="RELIANCE,INFY,TCS")
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()
    main(args.symbols.split(","), args.duration)
```

### Configuration: `config.yaml`

```yaml
brokers:
  - name: "paper_primary"
    type: "paper"
    label: "Paper-A"

  - name: "paper_secondary"
    type: "paper"
    label: "Paper-B"

  # Uncomment for live brokers (requires credentials)
  # - name: "dhan"
  #   type: "dhan"
  #   label: "Dhan"
  #   client_id: "${DHAN_CLIENT_ID}"
  #   access_token: "${DHAN_ACCESS_TOKEN}"

  # - name: "upstox"
  #   type: "upstox"
  #   label: "Upstox"
  #   client_id: "${UPSTOX_CLIENT_ID}"
  #   access_token: "${UPSTOX_ACCESS_TOKEN}"

symbols:
  - RELIANCE
  - INFY
  - TCS
  - HDFCBANK
  - ITC

monitoring:
  poll_interval_sec: 5
  min_spread_pct: 0.1     # Alert if spread exceeds this %
  max_spread_pct: 1.0     # High-confidence arbitrage threshold
  log_file: "arbitrage_log.json"

alerts:
  # Display settings
  show_all: false          # Show all comparisons (verbose)
  highlight_threshold: 0.2  # Highlight spreads above this %
  color: true              # ANSI color in terminal
```

### Broker Connector: `broker_connector.py`

```python
"""Multi-broker session management."""

from __future__ import annotations
import tradex


def connect_brokers(symbols: list[str]) -> list[dict]:
    """Connect to all configured brokers and return session map."""
    # Load config
    # For each broker config, call tradex.connect(broker_type, ...)
    # Build {broker_label: session} map
    # Return connected sessions
    ...
```

### Expected Output

```
Connected to 2 broker(s): Paper-A, Paper-B

╔══════════════════════════════════════════════════════════════╗
║ Multi-Broker Price Comparison                 2026-07-12     ║
╠══════════════════════════════════════════════════════════════╣
║ Symbol     Paper-A     Paper-B     Spread    Spread%   Flag  ║
║ RELIANCE   2487.50     2487.50     0.00      0.00%     —    ║
║ INFY       1565.30     1565.30     0.00      0.00%     —    ║
║ TCS        3840.00     3840.00     0.00      0.00%     —    ║
╚══════════════════════════════════════════════════════════════╝

Arbitrage opportunities: 0 (paper broker returns identical prices)
Note: Connect live brokers for real price discrepancies.

Duration: 120s | Elapsed: 5s | Polls: 1
All broker connections closed.
```

### Configuration Requirements

| Config Key | Required | Default | Notes |
|------------|----------|---------|-------|
| `brokers` | Yes | `[]` | List of broker configs |
| `brokers[].type` | Yes | — | `paper`, `dhan`, `upstox` |
| `brokers[].label` | No | `type` | Display label |
| `symbols` | Yes | `RELIANCE,INFY,TCS` | Symbols to monitor |
| `monitoring.poll_interval_sec` | No | `5` | Comparison poll interval |
| `monitoring.min_spread_pct` | No | `0.1` | Alert threshold % |
| `alerts.color` | No | `true` | ANSI color in terminal |

---

## How to Run

Each application follows the same pattern:

```bash
# From repo root
cd examples/<app_name>
python main.py                    # Default config
python main.py --help             # Show options
python main.py --config custom.yaml  # Custom config
```

All applications require the project to be installed in development mode:

```bash
pip install -e ".[dev]"
```

## Cross-References

| App | Related Notebook | Related Existing Example |
|-----|-----------------|------------------------|
| Market Scanner | Notebook 3 (Strategy Dev) | `broker_usage_demo.py` |
| Real-Time Dashboard | Notebook 5 (Portfolio) | `live_data_flow_test.py` |
| Backtest Runner | Notebook 3 (Strategy Dev) | `object_model_quickstart.py` |
| Multi-Broker Monitor | Notebook 6 (Certification) | `live_connection_test.py` |

## Implementation Order

1. **App 3 (Backtest Runner)** — leverages existing `analytics.backtest` modules
2. **App 1 (Market Scanner)** — leverages existing `analytics.scanner` modules
3. **App 4 (Multi-Broker Monitor)** — extends existing connectivity patterns
4. **App 2 (Real-Time Dashboard)** — most complex, needs terminal rendering

## Quality Standards

- Each app runs standalone with `python main.py`
- Each app works with paper broker (no credentials)
- Each app includes graceful degradation for empty data
- Each app has a `README.md` with setup instructions
- Each app uses `tradex.connect()` as the single entry point
- Configuration via YAML (not hardcoded values)
- Cleanup in `finally` blocks (always close sessions)
