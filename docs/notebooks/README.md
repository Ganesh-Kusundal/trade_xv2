# Interactive Notebooks — Phase 4 D4.5

> **Purpose:** 6 Jupyter notebooks covering every major TradeXV2 workflow.
> All notebooks run against the **paper broker** (no credentials required).
> Existing low-level broker notebooks live in `src/brokers/notebooks/` — these
> six extend and formalize them into production-grade guides.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| Python | ≥ 3.11 |
| Packages | `tradex`, `pandas`, `matplotlib`, `numpy` (pre-installed in project venv) |
| Kernel | `jupyter notebook` or `jupyter lab` |
| Broker | **Paper only** — set `TRAADEX_BROKER=paper` or pass `"paper"` to `tradex.connect()` |

```bash
# From repo root
pip install -e ".[notebooks]"
jupyter lab docs/notebooks/
```

---

## Existing Broker Notebooks

The following notebooks already exist in `src/brokers/notebooks/` and cover
low-level broker adapter testing. Our new notebooks build on top of the
product API (`tradex.connect()`).

| # | Existing Notebook | Coverage |
|---|-------------------|----------|
| 01 | `01_authentication.ipynb` | Broker auth handshake |
| 02 | `02_search_instrument.ipynb` | Instrument lookup |
| 03 | `03_get_quote.ipynb` | Single quote fetch |
| 04 | `04_historical.ipynb` | Historical bars |
| 05 | `05_live_stream.ipynb` | WebSocket tick stream |
| 06 | `06_market_depth.ipynb` | 20-level order book |
| 07 | `07_option_chain.ipynb` | Option chain + Greeks |
| 08 | `08_orders.ipynb` | Order placement |
| 09 | `09_portfolio.ipynb` | Portfolio view |
| 10 | `10_positions.ipynb` | Position list |
| 11 | `11_holdings.ipynb` | Holdings |
| 12 | `12_funds.ipynb` | Account funds |
| 13 | `13_benchmark.ipynb` | Broker benchmark |
| 14–19 | `14_diagnostics` … `19_performance` | Diagnostics, mapping, error handling, replay, perf |

---

## Notebook 1: Quickstart

> **Goal:** Get from zero to a placed order in under 10 minutes.

**File:** `01_quickstart.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, learning objectives, prerequisites | — |
| 2 | Code | `import tradex` + connect to paper broker | `Connected: paper …` |
| 3 | Markdown | Explain session/universe/instrument hierarchy | — |
| 4 | Code | `stock = session.universe.equity("RELIANCE")` + `stock.refresh()` | LTP, bid, ask |
| 5 | Code | `stock.history(timeframe="1D", days=30)` — fetch historical bars | Bar count, date range |
| 6 | Markdown | Explain quote vs. historical vs. live stream | — |
| 7 | Code | Place a paper buy order: `stock.buy(1, price=Decimal("2500"))` | Order ID, success flag |
| 8 | Code | `session.account.refresh()` → `session.account.funds` | Available balance |
| 9 | Code | `session.account.refresh()` → `session.account.positions` | Position table |
| 10 | Code | `session.close()` | `Session closed` |
| 11 | Markdown | Summary + links to deeper notebooks | — |

### Key Imports

```python
import tradex
from decimal import Decimal
```

### Expected Output

```
Connected: paper (session-id=abc123)
RELIANCE LTP: 2487.50  bid=2487.00  ask=2488.00
History bars: 30
Buy order: success=True  order_id=PAPER-001
Funds available: 1000000.00
Positions: 1 (RELIANCE qty=1)
Session closed
```

### Prerequisites

Paper broker only. No external API keys.

---

## Notebook 2: Historical Analysis

> **Goal:** Download data, compute indicators, and identify support/resistance levels.

**File:** `02_historical_analysis.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, objectives (indicator computation, S/R levels) | — |
| 2 | Code | Connect to paper, fetch 6 months of daily history | Bar count, date range |
| 3 | Code | Convert `HistoricalSeries` to `pandas.DataFrame` with OHLCV columns | DataFrame shape |
| 4 | Markdown | Explain indicator pipeline — RSI, MACD, SMA, ATR, VWAP | — |
| 5 | Code | Compute indicators using `domain.indicators` module | `Indicators(instrument)` |
| 6 | Code | `RSI(14)` → add RSI column to DataFrame | RSI values |
| 7 | Code | `MACD(fast=12, slow=26, signal=9)` → MACD + signal lines | MACD histogram |
| 8 | Code | `SMA(20)` and `SMA(50)` → moving averages | SMA columns |
| 9 | Markdown | Explain support/resistance identification (pivot points, local extrema) | — |
| 10 | Code | Compute pivot points from OHLC: `pivot = (H+L+C)/3` | S1, S2, R1, R2 |
| 11 | Code | Local extrema detection via `numpy` rolling min/max | Support/resistance levels |
| 12 | Markdown | Explain visualization approach | — |
| 13 | Code | Plot candlestick chart with `matplotlib` (or `mplfinance`) | Price chart |
| 14 | Code | Overlay SMA-20, SMA-50, RSI subplot, MACD subplot | 3-panel chart |
| 15 | Code | Annotate support/resistance horizontal lines on chart | Annotated chart |
| 16 | Code | Print summary: current trend, RSI zone, distance to nearest S/R | Text summary |
| 17 | Code | `session.close()` | `Session closed` |
| 18 | Markdown | Next steps → Notebook 3 (Strategy Development) | — |

### Key Imports

```python
import tradex
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from domain.indicators import RSI, MACD, ATR, VWAP
from domain.indicators.indicators import Indicators
```

### Expected Output

```
Fetched 126 daily bars for RELIANCE (2026-01-05 → 2026-07-11)
RSI(14) latest: 58.3
MACD: 12.45  Signal: 8.21  Histogram: 4.24
SMA-20: 2478.30  SMA-50: 2432.15
Support levels: [2410.00, 2385.50, 2320.00]
Resistance levels: [2510.00, 2545.00, 2590.00]
```

### Prerequisites

Paper broker. `matplotlib`, `pandas`, `numpy` installed.

---

## Notebook 3: Strategy Development

> **Goal:** Build a moving-average crossover strategy, backtest it, and optimize parameters.

**File:** `03_strategy_development.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, objectives (strategy design, backtest, optimization) | — |
| 2 | Code | Connect to paper, load historical data for NIFTY | — |
| 3 | Markdown | Explain `BacktestEngine` architecture and data flow | — |
| 4 | Code | Build `FeaturePipeline` with SMA(10), SMA(50), RSI(14), ATR(14) | Pipeline object |
| 5 | Code | Define crossover strategy logic (long when fast > slow, exit when fast < slow) | Strategy callable |
| 6 | Code | Configure `BacktestConfig`: initial_capital=1000000, commission=0.03% | Config object |
| 7 | Code | Instantiate `BacktestEngine` and `run()` the backtest | `BacktestResult` |
| 8 | Markdown | Explain performance metrics: Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor | — |
| 9 | Code | Access `BacktestMetrics` from result and display as DataFrame | Metrics table |
| 10 | Code | Plot equity curve from result trades | Equity line chart |
| 11 | Code | Plot drawdown from equity curve | Drawdown chart |
| 12 | Markdown | Explain parameter optimization (grid search over SMA periods) | — |
| 13 | Code | Build `ParamGrid` with fast=[5,10,20] and slow=[30,50,100] | Grid definition |
| 14 | Code | Run `OptimizationResult` via grid search | Results DataFrame |
| 15 | Code | Display best parameters and compare metrics across grid | Comparison table |
| 16 | Code | Plot parameter heatmap (fast vs slow → Sharpe ratio) | Heatmap |
| 17 | Code | `session.close()` | `Session closed` |
| 18 | Markdown | Next steps → Notebook 4 (Options Analysis) | — |

### Key Imports

```python
import tradex
import pandas as pd
from analytics.backtest import BacktestConfig, BacktestEngine
from analytics.backtest.optimizer import ParamGrid, OptimizationResult
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.pipeline.features import SMA, RSI, ATR, ROC, Momentum, Trend
```

### Expected Output

```
Backtest complete: 126 bars processed
Total return: 14.32%  Sharpe: 1.87  Max drawdown: -8.21%
Win rate: 58.3%  Profit factor: 1.64  Total trades: 18

Optimization (9 combinations):
  Best: fast=10, slow=50  → Sharpe 2.12, Return 18.7%
  Worst: fast=5, slow=100 → Sharpe 0.43, Return 3.1%
```

### Prerequisites

Paper broker. `analytics.backtest`, `analytics.pipeline`, `analytics.strategy` modules.

---

## Notebook 4: Options Analysis

> **Goal:** Fetch option chains, compute Greeks, analyze PCR/max pain, and visualize IV surface.

**File:** `04_options_analysis.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, objectives (chain analysis, Greeks, PCR, max pain, IV surface) | — |
| 2 | Code | Connect to paper, create `session.universe.index("NIFTY")` | Index instrument |
| 3 | Code | Fetch option chain: `idx.option_chain(expiry="2026-07-31")` | Chain object |
| 4 | Markdown | Explain option chain structure — `OptionChain` → `OptionStrike` → `OptionLeg` | — |
| 5 | Code | Display chain as DataFrame: strike, call_ltp, call_oi, put_ltp, put_oi | Chain table |
| 6 | Code | Identify ATM strike: `chain.atm.strike` | ATM strike |
| 7 | Markdown | Explain Greeks computation (Delta, Gamma, Theta, Vega, Rho) | — |
| 8 | Code | Compute Greeks for ATM call and put using Black-Scholes | Greeks table |
| 9 | Code | Display Greeks sensitivity to spot price change | Sensitivity chart |
| 10 | Markdown | Explain PCR (Put/Call Ratio) and Max Pain | — |
| 11 | Code | Compute PCR: `chain.pcr()` | PCR value |
| 12 | Code | Compute max pain: `chain.max_pain()` | Max pain strike |
| 13 | Code | Plot PCR history (if available) or current PCR gauge | PCR chart |
| 14 | Markdown | Explain IV surface — strike vs expiry → implied volatility | — |
| 15 | Code | Compute IV for each strike using Newton-Raphson | IV by strike |
| 16 | Code | Plot IV smile/skew for current expiry | IV curve |
| 17 | Code | Plot 3D IV surface (strike × expiry × IV) if multi-expiry | Surface plot |
| 18 | Code | Summary: ATM IV, skew steepness, PCR sentiment, max pain distance | Text summary |
| 19 | Code | `session.close()` | `Session closed` |
| 20 | Markdown | Next steps → Notebook 5 (Portfolio Monitoring) | — |

### Key Imports

```python
import tradex
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from decimal import Decimal
from domain.options.option_chain import OptionChain
```

### Expected Output

```
NIFTY Option Chain (expiry=2026-07-31): 25 strikes
ATM Strike: 25000
PCR: 1.23 (mildly bullish)
Max Pain: 24900
ATM IV: 18.4%
IV Skew: 2.1% (25-delta put premium over call)
```

### Prerequisites

Paper broker. Paper may return empty chain — cells gracefully degrade with messages.

---

## Notebook 5: Portfolio Monitoring

> **Goal:** Build a real-time portfolio dashboard with P&L, sector exposure, and risk metrics.

**File:** `05_portfolio_monitoring.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, objectives (P&L, exposure, risk metrics) | — |
| 2 | Code | Connect to paper, `session.account.refresh()` | Account snapshot |
| 3 | Code | Fetch positions: `session.account.positions` | Positions DataFrame |
| 4 | Code | Fetch holdings: `session.account.holdings` (if available) | Holdings DataFrame |
| 5 | Markdown | Explain P&L computation (realized + unrealized) | — |
| 6 | Code | For each position, refresh quote and compute `unrealized_pnl = qty * (ltp - avg_price)` | P&L per position |
| 7 | Code | Total P&L = sum of realized + unrealized | Total P&L |
| 8 | Code | Plot P&L bar chart by symbol | Bar chart |
| 9 | Markdown | Explain sector exposure analysis | — |
| 10 | Code | Map symbols to sectors (NSE sector mapping) | Sector labels |
| 11 | Code | Group positions by sector, compute % allocation | Exposure pie chart |
| 12 | Code | Plot sector exposure donut chart | Donut chart |
| 13 | Markdown | Explain risk metrics: VaR, concentration, beta | — |
| 14 | Code | Compute portfolio VaR (historical simulation, 95%) | VaR value |
| 15 | Code | Compute concentration ratio (top-3 / total) | Concentration % |
| 16 | Code | Compute portfolio beta vs NIFTY (rolling 60-day) | Beta value |
| 17 | Code | Print risk dashboard summary table | Dashboard table |
| 18 | Code | `session.close()` | `Session closed` |
| 19 | Markdown | Next steps → Notebook 6 (Broker Certification) | — |

### Key Imports

```python
import tradex
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
```

### Expected Output

```
Account balance: ₹1,000,000
Positions: 3
  RELIANCE  qty=10  avg=2450  ltp=2487  pnl=+370
  INFY      qty=5   avg=1580  ltp=1565  pnl=-75
  TCS       qty=2   avg=3800  ltp=3840  pnl=+80
Total unrealized P&L: +₹375

Sector exposure:
  Technology:  45%
  Energy:      35%
  Financials:  20%

Risk metrics:
  95% VaR (1-day): ₹4,230
  Concentration (top-3): 100%
  Beta vs NIFTY: 0.92
```

### Prerequisites

Paper broker. Paper positions may be empty — cells handle gracefully.

---

## Notebook 6: Broker Certification

> **Goal:** Run the full broker certification suite, interpret results, and compare brokers.

**File:** `06_broker_certification.ipynb`

### Cell-by-Cell Outline

| Cell | Type | Description | Key Output |
|------|------|-------------|------------|
| 1 | Markdown | Title, objectives (certification workflow, interpretation, comparison) | — |
| 2 | Markdown | Explain certification tiers: T0 (connection), T1 (quotes), T2 (history), T3 (orders), T4 (full) | Tier table |
| 3 | Code | Import certification services: `from brokers.services import run_benchmark` | — |
| 4 | Code | Run T0 (connection) on paper: `run_benchmark("paper", tier="T0")` | T0 result |
| 5 | Code | Run T1 (quotes): `run_benchmark("paper", tier="T1")` | T1 result |
| 6 | Code | Run T2 (history): `run_benchmark("paper", tier="T2")` | T2 result |
| 7 | Code | Run T3 (orders): `run_benchmark("paper", tier="T3")` | T3 result |
| 8 | Code | Run T4 (full): `run_benchmark("paper", tier="T4")` | T4 result |
| 9 | Markdown | Explain report structure — pass/fail per tier, latency percentiles, error rates | — |
| 10 | Code | Print formatted report for each tier result | Report cards |
| 11 | Code | Aggregate results into comparison DataFrame | Comparison table |
| 12 | Markdown | Explain cross-broker comparison methodology | — |
| 13 | Code | Load historical certification artifacts from `docs/certification/artifacts/` | Artifact list |
| 14 | Code | Parse JSON artifacts, build comparison table across broker×tier | Cross-broker table |
| 15 | Code | Plot radar chart: broker performance across tiers | Radar chart |
| 16 | Code | Highlight gaps and recommendations | Recommendation text |
| 17 | Code | Save certification report to `docs/certification/` | Report file |
| 18 | Markdown | Summary + interpretation guide | — |

### Key Imports

```python
import tradex
from brokers.services import run_benchmark
import json
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
```

### Expected Output

```
Certification Report: Paper Broker
═══════════════════════════════════
T0 Connection:  ✅ PASS  (latency: 45ms)
T1 Quotes:      ✅ PASS  (latency: 120ms, 3/3 symbols)
T2 History:     ✅ PASS  (latency: 340ms, 252 bars)
T3 Orders:      ✅ PASS  (latency: 89ms, 5/5 order types)
T4 Full:        ✅ PASS  (all checks passed)

Overall: 5/5 tiers passed
Artifacts saved: docs/certification/artifacts/T0_paper_latest.json …
```

### Prerequisites

Paper broker. Certification artifacts in `docs/certification/artifacts/`.

---

## Cross-References

| Notebook | Depends On | Leads To |
|----------|-----------|----------|
| 01 Quickstart | — | 02, 03, 04, 05, 06 |
| 02 Historical Analysis | 01 | 03 |
| 03 Strategy Development | 01, 02 | 04, Sample App 3 |
| 04 Options Analysis | 01 | 05 |
| 05 Portfolio Monitoring | 01 | 06, Sample App 2 |
| 06 Broker Certification | 01 | Sample App 4 |

## Implementation Order

1. **Notebook 1 (Quickstart)** — foundation, validates SDK end-to-end
2. **Notebook 2 (Historical Analysis)** — builds data familiarity
3. **Notebook 3 (Strategy Development)** — core analytics workflow
4. **Notebook 4 (Options Analysis)** — specialized domain
5. **Notebook 5 (Portfolio Monitoring)** — operational workflow
6. **Notebook 6 (Broker Certification)** — quality assurance workflow

## Quality Standards

- Every code cell must execute without errors on paper broker
- Each notebook must include at least one visualization
- Markdown cells must explain *why*, not just *what*
- All imports at the top of each notebook (first code cell)
- Graceful degradation when paper broker returns empty data
- Output snapshots captured as cell outputs (for documentation)
