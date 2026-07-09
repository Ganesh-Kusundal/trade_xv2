# Analytics Scanner (live candidate path)

**Ownership (ENG-020):** This package is the **live / event-capable** scanner.

- Emits `CANDIDATE_GENERATED` events for `TradingOrchestrator`
- Used by CLI scanner commands and strategy automation

Do **not** import `datalake.scanner` for live trading workflows.
`datalake/scanner` is SQL research screening against Parquet/DuckDB only.

## Session entry (AN-010)

Recommended product path — **no dual-scanner merge**:

```python
import pandas as pd
import tradex
from analytics.scanner import MomentumScanner

session = tradex.connect("paper")  # or dhan/upstox mode="market" for live history
symbols = ["RELIANCE", "TCS", "INFY"]
frames = [
    session.universe.equity(s).history(timeframe="1D", days=60).to_dataframe()
    for s in symbols
]
universe = pd.concat(frames, ignore_index=True)
result = MomentumScanner(top_n=5).scan(universe)
session.close()
```

| Step | Surface |
|------|---------|
| Session | `tradex.connect(...)` |
| Instruments | `session.universe.equity(symbol)` |
| Bars | `instrument.history(...).to_dataframe()` (OHLCV + `symbol`) |
| Scan | `analytics.scanner.*Scanner.scan(universe_df)` |

Smoke: `tests/e2e/test_analytics_session_smoke.py`.
