"""One-time migration: seed universe_history table from CSV files.

Usage: python -m scripts.migration.seed_universe_history [--catalog market_data/catalog.duckdb]

Reads all CSV files from data/universes/ and data/sectors/
and registers them in the universe_history and symbol_metadata_history tables.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

_UNIVERSE_DIR = Path("data/universes")
_SECTOR_DIR = Path("data/sectors")
_SECTOR_MAPPING_FILE = _SECTOR_DIR / "nifty_sector_mapping.csv"


def _universe_name_from_filename(filename: str) -> str:
    stem = filename.replace(".csv", "")
    if stem.startswith("nifty"):
        return "NIFTY" + stem[5:]
    return stem.upper()


def seed_universe_history(catalog_path: str) -> None:
    from datalake.storage.catalog import DataCatalog

    catalog = DataCatalog(root=str(Path(catalog_path).parent))
    logger.info("Connected to catalog at %s", catalog_path)

    universe_files = sorted(_UNIVERSE_DIR.glob("*.csv"))
    for csv_path in universe_files:
        universe_name = _universe_name_from_filename(csv_path.name)
        import pandas as pd

        from domain.symbols import normalize_symbol
        df = pd.read_csv(csv_path)
        symbols = [normalize_symbol(s) for s in df["symbol"]]
        count = catalog.register_universe_snapshot(universe_name, symbols)
        logger.info(
            "Registered %d symbols in %s from %s", count, universe_name, csv_path.name
        )

    if _SECTOR_MAPPING_FILE.exists():
        import pandas as pd

        df = pd.read_csv(_SECTOR_MAPPING_FILE)
        symbol_count = 0
        for _, row in df.iterrows():
            catalog.register_symbol_metadata_snapshot(
                symbol=normalize_symbol(str(row["symbol"])),
                sector=str(row["sector"]).strip(),
            )
            symbol_count += 1
        logger.info("Registered metadata for %d symbols from sector mapping", symbol_count)
    else:
        logger.warning("Sector mapping file not found: %s", _SECTOR_MAPPING_FILE)

    catalog.close()
    logger.info("Migration complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed universe_history and symbol_metadata_history from CSVs"
    )
    parser.add_argument(
        "--catalog",
        default="market_data/catalog.duckdb",
        help="Path to the DuckDB catalog file (default: market_data/catalog.duckdb)",
    )
    args = parser.parse_args()
    seed_universe_history(args.catalog)


if __name__ == "__main__":
    main()
