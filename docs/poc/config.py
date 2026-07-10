"""Momentum Top Gainer PoC — Configuration."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "market_data"
CANDLES_DIR = DATA_ROOT / "equities" / "candles" / "timeframe=1m"
POC_DATA = PROJECT_ROOT / "poc" / "data"

# Output files
FEATURES_PATH = POC_DATA / "features.parquet"
LABELS_PATH = POC_DATA / "labels.parquet"
DATASET_PATH = POC_DATA / "dataset.parquet"
MODEL_PATH = POC_DATA / "model.pkl"
BACKTEST_PATH = POC_DATA / "backtest_results.json"
AUDIT_PATH = POC_DATA / "audit_report.json"

# Time windows
MARKET_OPEN = "09:15"
FEATURE_CUTOFF = "09:45"
LABEL_START = "09:45"
LABEL_END = "15:15"

# Labeling — target stocks that move ≥5% from 09:45→15:15
MIN_RETURN_PCT = 5.0  # Minimum return to be labeled as "top gainer"

# Features
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
RVOL_LOOKBACK_DAYS = 10
MOMENTUM_5D_LOOKBACK = 5

# Train / Test split
TRAIN_END_YEAR = 2024
TEST_START_YEAR = 2025
FIRST_TRAIN_END = 2022  # First window: 2021-2022 (NIFTY data starts 2021-06)

# Model
N_ESTIMATORS = 500
MAX_DEPTH = 6
LEARNING_RATE = 0.05
EARLY_STOPPING_ROUNDS = 50
CV_FOLDS = 5

# Backtest
TOP_K = 3  # Pick top-3 stocks per day
BROKERAGE_PCT = 0.05
