"""Refresh stale symbols - force re-download for symbols with outdated data."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datalake.storage.catalog import DataCatalog
from datalake.ingestion.loader import HistoricalDataLoader

logger = logging.getLogger(__name__)


def identify_stale_symbols(
    catalog_path: str = "market_data",
    max_age_days: int = 7,
) -> list[dict]:
    """Identify symbols with data older than max_age_days."""
    conn = duckdb.connect(catalog_path, read_only=True)

    try:
        result = conn.execute(
            """
            SELECT
                symbol,
                MAX(timestamp)::DATE as latest_date,
                DATEDIFF('day', MAX(timestamp)::DATE, CURRENT_DATE) as days_old
            FROM symbols
            GROUP BY symbol
            HAVING MAX(timestamp) < CURRENT_DATE - INTERVAL ? DAY
            ORDER BY days_old DESC
        """,
            [max_age_days],
        ).fetchall()

        return [{"symbol": row[0], "latest_date": row[1], "days_old": row[2]} for row in result]
    finally:
        conn.close()


def refresh_symbols(
    symbols: list[str],
    gateway,
    years: int = 5,
    timeframe: str = "1m",
    exchange: str = "NSE",
) -> dict:
    """Force re-download symbols with extended date range."""
    catalog = DataCatalog(root="market_data")
    loader = HistoricalDataLoader(root="market_data", catalog=catalog)

    results = {}
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] Refreshing {symbol}...")

        # Download with extended range
        result = loader.download_symbol(
            symbol=symbol,
            gateway=gateway,
            years=years,
            timeframe=timeframe,
            exchange=exchange,
        )

        results[symbol] = result

        if result["rows"] > 0:
            print(f"  ✓ Downloaded {result['rows']:,} rows")
            if result["duplicates_dropped"] > 0:
                print(f"    - Dropped {result['duplicates_dropped']} duplicates")
            if result["invalid_dropped"] > 0:
                print(f"    - Dropped {result['invalid_dropped']} invalid rows")
        else:
            print(f"  ✗ No data returned")

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Refresh stale symbols")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["GSPL", "CHOLAFIN", "MOTHERSON"],
        help="Symbols to refresh (default: GSPL, CHOLAFIN, MOTHERSON)",
    )
    parser.add_argument("--years", type=int, default=5, help="Years of history")
    parser.add_argument("--timeframe", default="1m", help="Candle timeframe")
    parser.add_argument("--exchange", default="NSE", help="Exchange")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only identify stale symbols, don't refresh",
    )
    args = parser.parse_args()

    from infrastructure.logging_config import configure_logging

    configure_logging()

    # Identify stale symbols
    print("Identifying stale symbols...")
    stale = identify_stale_symbols(max_age_days=7)

    if not stale:
        print("✓ No stale symbols found!")
        return

    print(f"\nFound {len(stale)} stale symbols:")
    for s in stale:
        print(f"  {s['symbol']}: {s['latest_date']} ({s['days_old']} days old)")

    if args.check_only:
        return

    # Try to create gateway
    try:
        from pathlib import Path

        from interface.ui.services.broker_registry import create_gateway

        gateway = create_gateway("dhan", env_path=Path(".env.local"), load_instruments=True)
        if not gateway:
            print("\n✗ Failed to create Dhan gateway. Check .env.local configuration.")
            return
    except Exception as e:
        print(f"\n✗ Failed to create gateway: {e}")
        print("  Make sure .env.local is configured with Dhan credentials.")
        return

    # Refresh symbols
    print(f"\nRefreshing {len(args.symbols)} symbols...")
    results = refresh_symbols(
        symbols=args.symbols,
        gateway=gateway,
        years=args.years,
        timeframe=args.timeframe,
        exchange=args.exchange,
    )

    # Summary
    print("\n" + "=" * 80)
    print("REFRESH SUMMARY")
    print("=" * 80)

    total_rows = sum(r["rows"] for r in results.values())
    successful = sum(1 for r in results.values() if r["rows"] > 0)
    failed = len(results) - successful

    print(f"Total symbols: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total rows downloaded: {total_rows:,}")

    if failed > 0:
        print("\nFailed symbols:")
        for symbol, result in results.items():
            if result["rows"] == 0:
                print(f"  ✗ {symbol}")


if __name__ == "__main__":
    main()
