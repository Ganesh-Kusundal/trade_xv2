"""Identify and handle index symbols mixed with equity data."""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# Known Indian indices
KNOWN_INDICES = {
    "NIFTY",
    "NIFTY50",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "SENSEX",
    "SENSEX50",
    "BANKEX",
    "NIFTYNXT50",
    "NIFTY100",
    "NIFTY200",
    "NIFTY500",
    "NIFTYINFRA",
    "NIFTYIT",
    "NIFTYPHARMA",
    "NIFTYFMCG",
    "INDIAVIX",
}


def identify_index_symbols(catalog_path: str = "market_data/catalog.duckdb") -> list[str]:
    """Find symbols that are likely indices based on naming patterns."""
    conn = duckdb.connect(catalog_path, read_only=True)

    try:
        # Get all symbols
        result = conn.execute("SELECT symbol FROM symbols").fetchall()
        all_symbols = [row[0] for row in result]

        # Identify indices
        indices = []
        for symbol in all_symbols:
            # Check against known indices
            if symbol in KNOWN_INDICES:
                indices.append(symbol)
                continue

            # Check for index-like patterns
            if any(pattern in symbol for pattern in ["NIFTY", "SENSEX", "BANKEX", "VIX"]):
                indices.append(symbol)

        return indices
    finally:
        conn.close()


def mark_as_indices(
    symbols: list[str],
    catalog_path: str = "market_data/catalog.duckdb",
) -> None:
    """Update catalog to mark symbols as indices."""
    conn = duckdb.connect(catalog_path)

    try:
        for symbol in symbols:
            conn.execute(
                """
                UPDATE symbols
                SET instrument_type = 'INDEX',
                    exchange = 'NSE_INDEX'
                WHERE symbol = ?
            """,
                [symbol],
            )
            logger.info("Marked %s as INDEX", symbol)

        conn.commit()
        print(f"✓ Marked {len(symbols)} symbols as indices")
    finally:
        conn.close()


def move_to_separate_directory(
    symbols: list[str],
    root: str = "market_data",
) -> None:
    """Move index Parquet files to separate directory."""
    root_path = Path(root)
    equity_dir = root_path / "equities" / "candles" / "timeframe=1m"
    index_dir = root_path / "indices" / "candles" / "timeframe=1m"
    index_dir.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        src = equity_dir / f"symbol={symbol}"
        dst = index_dir / f"symbol={symbol}"

        if src.exists():
            # Move directory
            if dst.exists():
                dst.rmdir()
            src.rename(dst)
            logger.info("Moved %s to indices directory", symbol)

    print(f"✓ Moved {len(symbols)} index directories")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Handle index symbols")
    parser.add_argument(
        "--identify",
        action="store_true",
        help="Only identify index symbols",
    )
    parser.add_argument(
        "--mark",
        action="store_true",
        help="Mark indices in catalog",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move index files to separate directory",
    )
    args = parser.parse_args()

    from infrastructure.logging_config import configure_logging

    configure_logging()

    # Identify indices
    print("Identifying index symbols...")
    indices = identify_index_symbols()

    if not indices:
        print("✓ No index symbols found in equity data")
        return

    print(f"\nFound {len(indices)} index symbols:")
    for idx in indices:
        print(f"  - {idx}")

    if args.identify:
        return

    # Mark in catalog
    if args.mark or args.move:
        print("\nMarking indices in catalog...")
        mark_as_indices(indices)

    # Move files
    if args.move:
        print("\nMoving index files...")
        move_to_separate_directory(indices)

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
