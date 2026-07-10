# Momentum Top Gainer Predictor — PoC

## Goal
Predict which NSE stocks will close in the top 5% of daily returns
between 09:45 AM and 15:15 PM, using features computed at 09:45.

## Data Source
- `market_data/equities/candles/timeframe=1m/symbol=*/data.parquet`
- 501 NSE equity symbols, 2020-01-01 to 2026-06-10
- Columns: timestamp, symbol, exchange, open, high, low, close, volume, oi

## Files
| File | Purpose |
|------|---------|
| `config.py` | Constants and configuration |
| `data_audit.py` | Verify data completeness and quality |
| `features.py` | Compute 20+ momentum indicators at 09:45 |
| `labels.py` | Label top 5% gainers per trading day |
| `train.py` | Train XGBoost classifier with time-series CV |
| `backtest.py` | Simulate trades and evaluate performance |

## Run Order
```bash
python poc/data_audit.py      # Step 1: Check data quality
python poc/features.py        # Step 2: Compute features -> poc/data/features.parquet
python poc/labels.py          # Step 3: Generate labels -> poc/data/labels.parquet
python poc/train.py           # Step 4: Train model -> poc/data/model.pkl
python poc/backtest.py        # Step 5: Backtest -> poc/data/backtest_results.json
```

## Approach
1. **Reverse Engineering**: For each day, identify top 5% gainers (09:45→15:15 return)
2. **Feature Extraction**: Compute indicators ONLY at 09:45 (no lookahead)
3. **Time-Series Split**: Train on 2020-2024, test on 2025-2026
4. **XGBoost Classifier**: Predict probability of being a top gainer
5. **Backtest**: Buy top-K predictions at 09:45, sell at 15:15
