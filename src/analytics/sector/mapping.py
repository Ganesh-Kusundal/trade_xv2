"""Sector mapping — load and query stock-to-sector relationships.

Provides:
    - Load sector mapping from CSV or dict
    - Query which sector a symbol belongs to
    - Get all symbols in a sector
    - Get all sectors

Usage:
    mapper = SectorMapper.load_csv("data/sectors/nifty_sector_mapping.csv")
    sector = mapper.get_sector("RELIANCE")  # "OilGas"
    symbols = mapper.get_symbols("IT")  # ["TCS", "INFY", ...]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)

# Default NIFTY sector mapping (embedded for offline use)
DEFAULT_SECTOR_MAP: dict[str, str] = {
    # IT
    "TCS": "IT",
    "INFY": "IT",
    "HCLTECH": "IT",
    "WIPRO": "IT",
    "TECHM": "IT",
    "LTTS": "IT",
    "PERSISTENT": "IT",
    "COFORGE": "IT",
    "MPHASIS": "IT",
    "KPITTECH": "IT",
    "BSOFT": "IT",
    "CYIENT": "IT",
    "ZENSARTECH": "IT",
    "TATAELXSI": "IT",
    "HAPPSTMNDS": "IT",
    "INTELLECT": "IT",
    "CDSL": "IT",
    # Finance (includes Banking)
    "HDFCBANK": "Finance",
    "ICICIBANK": "Finance",
    "KOTAKBANK": "Finance",
    "AXISBANK": "Finance",
    "SBIN": "Finance",
    "INDUSINDBK": "Finance",
    "BANDHANBNK": "Finance",
    "FEDERALBNK": "Finance",
    "IDFCFIRSTB": "Finance",
    "PNB": "Finance",
    "BANKBARODA": "Finance",
    "BANKINDIA": "Finance",
    "UNIONBANK": "Finance",
    "CANBK": "Finance",
    "AUBANK": "Finance",
    "KARURVYSYA": "Finance",
    "BAJFINANCE": "Finance",
    "BAJAJFINSV": "Finance",
    "SBILIFE": "Finance",
    "HDFCLIFE": "Finance",
    "ICICIPRULI": "Finance",
    "MUTHOOTFIN": "Finance",
    "MANAPPURAM": "Finance",
    "CHOLAFIN": "Finance",
    "LICHSGFIN": "Finance",
    "SBICARD": "Finance",
    "SHRIRAMFIN": "Finance",
    "HDFCAMC": "Finance",
    # Oil & Gas
    "RELIANCE": "OilGas",
    "ONGC": "OilGas",
    "BPCL": "OilGas",
    "IOC": "OilGas",
    "GAIL": "OilGas",
    "PETRONET": "OilGas",
    "ATGL": "OilGas",
    "MGL": "OilGas",
    "HINDPETRO": "OilGas",
    "MRPL": "OilGas",
    # Auto
    "TATAMOTORS": "Auto",
    "M&M": "Auto",
    "MARUTI": "Auto",
    "HEROMOTOCO": "Auto",
    "BAJAJ-AUTO": "Auto",
    "EICHERMOT": "Auto",
    "TVSMOTOR": "Auto",
    "ASHOKLEY": "Auto",
    "MOTHERSON": "Auto",
    "BOSCHLTD": "Auto",
    "SONACOMS": "Auto",
    "APOLLOTYRE": "Auto",
    "BALKRISIND": "Auto",
    "EXIDEIND": "Auto",
    "AMARARAJA": "Auto",
    # Pharma
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "AUROPHARMA": "Pharma",
    "TORNTPHARM": "Pharma",
    "ALKEM": "Pharma",
    "LUPIN": "Pharma",
    "IPCALAB": "Pharma",
    "GLENMARK": "Pharma",
    "ZYDUSLIFE": "Pharma",
    "BIOCON": "Pharma",
    "LALPATHLAB": "Pharma",
    "METROPOLIS": "Pharma",
    "APOLLOHOSP": "Pharma",
    # FMCG
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "MARICO": "FMCG",
    "DABUR": "FMCG",
    "COLPAL": "FMCG",
    "GODREJCP": "FMCG",
    "EMAMILTD": "FMCG",
    "RADICO": "FMCG",
    "TATACONSUM": "FMCG",
    "BATAINDIA": "FMCG",
    # Metals
    "TATASTEEL": "Metals",
    "HINDALCO": "Metals",
    "JSWSTEEL": "Metals",
    "VEDL": "Metals",
    "NMDC": "Metals",
    "COALINDIA": "Metals",
    "NATIONALUM": "Metals",
    "HINDZINC": "Metals",
    "RATNAMANI": "Metals",
    "APLAPOLLO": "Metals",
    "JINDALSTEL": "Metals",
    "SAIL": "Metals",
    # Realty
    "DLF": "Realty",
    "GODREJPROP": "Realty",
    "OBEROIRLTY": "Realty",
    "PRESTIGE": "Realty",
    "BRIGADE": "Realty",
    "SOBHA": "Realty",
    "PHOENIXLTD": "Realty",
    "LODHA": "Realty",
    # Infrastructure (Power + Construction)
    "LT": "Infrastructure",
    "ADANIENT": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "ADANIGREEN": "Infrastructure",
    "NTPC": "Power",
    "POWERGRID": "Power",
    "TATAPOWER": "Power",
    "SJVN": "Power",
    "NHPC": "Power",
    "KEC": "Infrastructure",
    # Chemicals
    "DEEPAKNTR": "Chemicals",
    "ATUL": "Chemicals",
    "NAVINFLUOR": "Chemicals",
    "SRF": "Chemicals",
    "PIIND": "Chemicals",
    "TATACHEM": "Chemicals",
    "GSFC": "Chemicals",
    "GNFC": "Chemicals",
    # Cement
    "ULTRACEMCO": "Cement",
    "ACC": "Cement",
    "AMBUJACEM": "Cement",
    "DALBHARAT": "Cement",
    "JKCEMENT": "Cement",
    "SHREECEM": "Cement",
    # Consumer Durables
    "VOLTAS": "ConsumerDur",
    "BLUESTARCO": "ConsumerDur",
    "DIXON": "ConsumerDur",
    "RAJESHEXPO": "ConsumerDur",
    "TITAN": "ConsumerDur",
    # Media
    "ZEEL": "Media",
    "SUNTV": "Media",
    "PVRINOX": "Media",
    # Consumer Services (includes Platform/Retail)
    "ZOMATO": "ConsumerServices",
    "PAYTM": "ConsumerServices",
    "POLICYBZR": "ConsumerServices",
    "NYKAA": "ConsumerServices",
    "TRENT": "ConsumerServices",
    "AVENUE": "ConsumerServices",
    # Capital Goods
    "POLYCAB": "CapitalGoods",
    "KEI": "CapitalGoods",
    "ASTRAL": "CapitalGoods",
    # Misc
    "IRCTC": "Misc",
    "IEX": "Misc",
    "BECTORFOOD": "Misc",
}


@dataclass
class SectorMapper:
    """Maps stock symbols to their sector and vice versa."""

    _symbol_to_sector: dict[str, str] = field(default_factory=dict)
    _sector_to_symbols: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load_csv(cls, path: str | Path) -> SectorMapper:
        """Load sector mapping from a CSV with 'symbol' and 'sector' columns."""
        df = pd.read_csv(path)
        if "symbol" not in df.columns or "sector" not in df.columns:
            raise ValueError(
                f"CSV must have 'symbol' and 'sector' columns, got: {list(df.columns)}"
            )
        mapping = dict(zip(df["symbol"].str.upper(), df["sector"], strict=False))
        return cls.from_dict(mapping)

    @classmethod
    def from_dict(cls, mapping: dict[str, str]) -> SectorMapper:
        """Create mapper from a {symbol: sector} dict."""
        sym2sec = {k.upper(): v for k, v in mapping.items()}
        sec2sym: dict[str, list[str]] = {}
        for sym, sec in sym2sec.items():
            sec2sym.setdefault(sec, []).append(sym)
        return cls(_symbol_to_sector=sym2sec, _sector_to_symbols=sec2sym)

    @classmethod
    def default(cls) -> SectorMapper:
        """Return the built-in NIFTY sector mapping."""
        return cls.from_dict(DEFAULT_SECTOR_MAP)

    def get_sector(self, symbol: str) -> str | None:
        """Return the sector for a symbol, or None if unmapped."""
        return self._symbol_to_sector.get(normalize_symbol(symbol))

    def get_symbols(self, sector: str) -> list[str]:
        """Return all symbols in a sector."""
        return list(self._sector_to_symbols.get(sector, []))

    @property
    def sectors(self) -> list[str]:
        """All known sector names, sorted."""
        return sorted(self._sector_to_symbols.keys())

    @property
    def total_symbols(self) -> int:
        return len(self._symbol_to_sector)

    def sector_counts(self) -> dict[str, int]:
        """Number of symbols per sector."""
        return {sec: len(syms) for sec, syms in sorted(self._sector_to_symbols.items())}

    def assign_sectors(self, df: pd.DataFrame, symbol_col: str = "symbol") -> pd.DataFrame:
        """Add a 'sector' column to a DataFrame based on a symbol column."""
        result = df.copy()
        result["sector"] = (
            result[symbol_col].str.upper().map(self._symbol_to_sector).fillna("Unknown")
        )
        return result
