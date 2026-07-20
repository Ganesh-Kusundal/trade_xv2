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

# Preferred on-disk mapping (NSE NIFTY500 industry → short sector tags).
_SECTOR_CSV_CANDIDATES = (
    Path("data/sectors/nifty_sector_mapping.csv"),
    Path("data/sectors/ind_nifty500list.csv"),
)

# NSE ind_nifty500list "Industry" → short tags used by DiversifiedTopK / analytics.
NSE_INDUSTRY_TO_SECTOR: dict[str, str] = {
    "Automobile and Auto Components": "Auto",
    "Capital Goods": "CapitalGoods",
    "Chemicals": "Chemicals",
    "Construction": "Infrastructure",
    "Construction Materials": "Cement",
    "Consumer Durables": "ConsumerDur",
    "Consumer Services": "ConsumerServices",
    "Diversified": "Diversified",
    "Fast Moving Consumer Goods": "FMCG",
    "Financial Services": "Finance",
    "Healthcare": "Pharma",
    "Information Technology": "IT",
    "Media Entertainment & Publication": "Media",
    "Metals & Mining": "Metals",
    "Oil Gas & Consumable Fuels": "OilGas",
    "Power": "Power",
    "Realty": "Realty",
    "Services": "Services",
    "Telecommunication": "Telecom",
    "Textiles": "Textiles",
}


def _nse_industry_to_sector(industry: str) -> str:
    return NSE_INDUSTRY_TO_SECTOR.get(industry, industry)


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
        """Load sector mapping from a CSV with symbol/sector columns."""
        return cls.from_dict(cls._mapping_from_csv(path))

    @staticmethod
    def _mapping_from_csv(path: str | Path) -> dict[str, str]:
        """Read ``symbol,sector`` or NSE ``Symbol,Industry`` CSV into a mapping."""
        df = pd.read_csv(path)
        cols = {c.lower(): c for c in df.columns}
        if "symbol" in cols and "sector" in cols:
            sym_col, sec_col = cols["symbol"], cols["sector"]
        elif "symbol" in cols and "industry" in cols:
            # NSE ind_nifty500list.csv shape
            sym_col, ind_col = cols["symbol"], cols["industry"]
            return {
                str(s).upper(): _nse_industry_to_sector(str(i))
                for s, i in zip(df[sym_col], df[ind_col], strict=False)
                if pd.notna(s) and pd.notna(i)
            }
        else:
            raise ValueError(
                f"CSV must have symbol+sector or Symbol+Industry columns, got: {list(df.columns)}"
            )
        return {
            str(s).upper(): str(sec)
            for s, sec in zip(df[sym_col], df[sec_col], strict=False)
            if pd.notna(s) and pd.notna(sec)
        }

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
        """Load on-disk NIFTY500 sector CSV when present; else embedded defaults.

        CSV fills coverage for the full NIFTY500 universe; embedded
        ``DEFAULT_SECTOR_MAP`` remains a bootstrap fallback and fills gaps.
        """
        mapping = dict(DEFAULT_SECTOR_MAP)
        for path in _SECTOR_CSV_CANDIDATES:
            if path.exists():
                try:
                    mapping.update(cls._mapping_from_csv(path))
                    logger.info("SectorMapper loaded %d symbols from %s", len(mapping), path)
                    break
                except (OSError, ValueError) as exc:
                    logger.warning("Failed to load sector CSV %s: %s", path, exc)
        return cls.from_dict(mapping)

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
