"""Add sector classification and sector-level features to the feature set.

Computes per-sector aggregates at 09:45 each day:
  - sector_mom_30m: average ret_30m of stocks in the sector
  - sector_rvol: average rvol of stocks in the sector
  - sector_beats_nifty_pct: fraction of sector stocks beating NIFTY
  - sector_mom_5d: average 5d momentum of stocks in the sector
  - sector_rank: sector rank by aggregate momentum
  - sector_deviation: stock ret_30m minus sector avg ret_30m

Saves enhanced features to features_with_sector.parquet
"""

from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = PROJECT_ROOT / "poc" / "data" / "features.parquet"
POC_DATA = PROJECT_ROOT / "poc" / "data"
OUTPUT_PATH = POC_DATA / "features_with_sector.parquet"

# NIFTY sector mapping (copied from analytics.sector.mapping.DEFAULT_SECTOR_MAP
# to avoid circular imports from the analytics package)
DEFAULT_SECTOR_MAP: dict[str, str] = {
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT",
    "LTTS": "IT", "PERSISTENT": "IT", "COFORGE": "IT", "MPHASIS": "IT",
    "KPITTECH": "IT", "BSOFT": "IT", "CYIENT": "IT", "ZENSARTECH": "IT",
    "TATAELXSI": "IT", "HAPPSTMNDS": "IT", "INTELLECT": "IT", "CDSL": "IT",
    "HDFCBANK": "Finance", "ICICIBANK": "Finance", "KOTAKBANK": "Finance",
    "AXISBANK": "Finance", "SBIN": "Finance", "INDUSINDBK": "Finance",
    "BANDHANBNK": "Finance", "FEDERALBNK": "Finance", "IDFCFIRSTB": "Finance",
    "PNB": "Finance", "BANKBARODA": "Finance", "BANKINDIA": "Finance",
    "UNIONBANK": "Finance", "CANBK": "Finance", "AUBANK": "Finance",
    "KARURVYSYA": "Finance", "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance",
    "SBILIFE": "Finance", "HDFCLIFE": "Finance", "ICICIPRULI": "Finance",
    "MUTHOOTFIN": "Finance", "MANAPPURAM": "Finance", "CHOLAFIN": "Finance",
    "LICHSGFIN": "Finance", "SBICARD": "Finance", "SHRIRAMFIN": "Finance",
    "HDFCAMC": "Finance",
    "RELIANCE": "OilGas", "ONGC": "OilGas", "BPCL": "OilGas", "IOC": "OilGas",
    "GAIL": "OilGas", "PETRONET": "OilGas", "ATGL": "OilGas", "MGL": "OilGas",
    "HINDPETRO": "OilGas", "MRPL": "OilGas",
    "TATAMOTORS": "Auto", "M&M": "Auto", "MARUTI": "Auto", "HEROMOTOCO": "Auto",
    "BAJAJ-AUTO": "Auto", "EICHERMOT": "Auto", "TVSMOTOR": "Auto", "ASHOKLEY": "Auto",
    "MOTHERSON": "Auto", "BOSCHLTD": "Auto", "SONACOMS": "Auto", "APOLLOTYRE": "Auto",
    "BALKRISIND": "Auto", "EXIDEIND": "Auto", "AMARARAJA": "Auto",
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma",
    "AUROPHARMA": "Pharma", "TORNTPHARM": "Pharma", "ALKEM": "Pharma", "LUPIN": "Pharma",
    "IPCALAB": "Pharma", "GLENMARK": "Pharma", "ZYDUSLIFE": "Pharma", "BIOCON": "Pharma",
    "LALPATHLAB": "Pharma", "METROPOLIS": "Pharma", "APOLLOHOSP": "Pharma",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "MARICO": "FMCG", "DABUR": "FMCG", "COLPAL": "FMCG", "GODREJCP": "FMCG",
    "EMAMILTD": "FMCG", "RADICO": "FMCG", "TATACONSUM": "FMCG", "BATAINDIA": "FMCG",
    "TATASTEEL": "Metals", "HINDALCO": "Metals", "JSWSTEEL": "Metals", "VEDL": "Metals",
    "NMDC": "Metals", "COALINDIA": "Metals", "NATIONALUM": "Metals", "HINDZINC": "Metals",
    "RATNAMANI": "Metals", "APLAPOLLO": "Metals", "JINDALSTEL": "Metals", "SAIL": "Metals",
    "DLF": "Realty", "GODREJPROP": "Realty", "OBEROIRLTY": "Realty", "PRESTIGE": "Realty",
    "BRIGADE": "Realty", "SOBHA": "Realty", "PHOENIXLTD": "Realty", "LODHA": "Realty",
    "LT": "Infrastructure", "ADANIENT": "Infrastructure", "ADANIPORTS": "Infrastructure",
    "ADANIGREEN": "Infrastructure", "KEC": "Infrastructure",
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power", "SJVN": "Power", "NHPC": "Power",
    "DEEPAKNTR": "Chemicals", "ATUL": "Chemicals", "NAVINFLUOR": "Chemicals", "SRF": "Chemicals",
    "PIIND": "Chemicals", "TATACHEM": "Chemicals", "GSFC": "Chemicals", "GNFC": "Chemicals",
    "ULTRACEMCO": "Cement", "ACC": "Cement", "AMBUJACEM": "Cement", "DALBHARAT": "Cement",
    "JKCEMENT": "Cement", "SHREECEM": "Cement",
    "VOLTAS": "ConsumerDur", "BLUESTARCO": "ConsumerDur", "DIXON": "ConsumerDur",
    "RAJESHEXPO": "ConsumerDur", "TITAN": "ConsumerDur",
    "ZEEL": "Media", "SUNTV": "Media", "PVRINOX": "Media",
    "ZOMATO": "ConsumerServices", "PAYTM": "ConsumerServices", "POLICYBZR": "ConsumerServices",
    "NYKAA": "ConsumerServices", "TRENT": "ConsumerServices", "AVENUE": "ConsumerServices",
    "POLYCAB": "CapitalGoods", "KEI": "CapitalGoods", "ASTRAL": "CapitalGoods",
    "IRCTC": "Misc", "IEX": "Misc", "BECTORFOOD": "Misc",
}


def add_sector_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add sector column and per-sector aggregate features."""
    result = df.copy()

    result["sector"] = result["symbol"].str.upper().map(DEFAULT_SECTOR_MAP).fillna("Unknown")

    known = (result["sector"] != "Unknown").sum()
    print(f"Mapped {known}/{len(result)} rows to sectors")

    sector_cols = ["date", "sector"]
    aggs = result[result["sector"] != "Unknown"].groupby(["date", "sector"]).agg(
        sector_mom_30m=("ret_30m", "mean"),
        sector_range_30m=("range_30m", "mean"),
        sector_rvol=("rvol", "mean"),
        sector_beats_nifty_pct=("beats_nifty_30m", "mean"),
        sector_mom_5d=("mom_5d", "mean"),
        sector_mom_10d=("mom_10d", "mean"),
        sector_vol_surge=("vol_surge", "mean"),
        sector_ret_1d_ago=("ret_1d_ago", "mean"),
        sector_obv_delta=("obv_delta", "mean"),
        sector_rel_strength=("rel_strength_30m", "mean"),
        sector_avg_vol=("avg_vol_30m", "mean"),
        sector_atr_ratio=("atr_ratio", "mean"),
        n_stocks=("ret_30m", "count"),
    ).reset_index()
    sector_cols.extend([c for c in aggs.columns if c not in ("date", "sector")])

    # Rank sectors per day
    aggs["sector_rank_mom"] = aggs.groupby("date")["sector_mom_30m"].rank(ascending=False)
    aggs["sector_rank_vol"] = aggs.groupby("date")["sector_rvol"].rank(ascending=False)
    aggs["sector_rank_combined"] = aggs["sector_rank_mom"] + aggs["sector_rank_vol"]

    # Top-3 leading sectors
    aggs["is_leading_sector"] = (
        aggs.groupby("date")["sector_rank_combined"].rank() <= 3
    ).astype(int)

    # Add rank columns to merge list (they were added AFTER sector_cols was built)
    rank_cols = ["sector_rank_mom", "sector_rank_vol", "sector_rank_combined", "is_leading_sector"]
    sector_cols.extend([c for c in rank_cols if c in aggs.columns])

    result = result.merge(aggs[sector_cols], on=["date", "sector"], how="left")

    # Stock deviation from sector average
    result["ret_deviation_from_sector"] = result["ret_30m"] - result["sector_mom_30m"]

    fill_cols = [c for c in sector_cols if c not in ("date", "sector")]
    for col in fill_cols:
        result[col] = result[col].fillna(0)
    result["ret_deviation_from_sector"] = result["ret_deviation_from_sector"].fillna(0)

    numeric_cols = result.select_dtypes(include=[np.number]).columns.tolist()
    result[numeric_cols] = result[numeric_cols].fillna(0)

    return result


def main() -> None:
    print(f"Loading features from {FEATURES_PATH}...")
    df = pd.read_parquet(FEATURES_PATH)
    print(f"Loaded {len(df):,} rows x {len(df.columns)} cols\n")

    enhanced = add_sector_features(df)

    POC_DATA.mkdir(parents=True, exist_ok=True)
    enhanced.to_parquet(str(OUTPUT_PATH), index=False)
    print(f"\nSaved enhanced features: {OUTPUT_PATH}")
    print(f"New columns: {len(enhanced.columns) - len(df.columns)}")


if __name__ == "__main__":
    main()
