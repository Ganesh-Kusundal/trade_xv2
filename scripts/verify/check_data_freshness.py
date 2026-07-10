"""Data freshness and completeness analysis."""

from datetime import date
from pathlib import Path

import duckdb

conn = duckdb.connect("market_data/catalog.duckdb", read_only=True)

print("=" * 80)
print("DATA FRESHNESS & COMPLETENESS REPORT")
print("=" * 80)

parquet_dir = Path("market_data/equities/candles/timeframe=1m")
parquet_pattern = str(parquet_dir / "symbol=*" / "data.parquet")

# 1. Data Freshness - How recent is the data?
print("\n📅 DATA FRESHNESS")
print("-" * 80)

today = date.today()
result = conn.execute(f"""
    SELECT
        MAX(latest_date) as most_recent_date,
        MIN(latest_date) as oldest_latest_date,
        COUNT(*) as total_symbols
    FROM (
        SELECT symbol, MAX(timestamp)::DATE as latest_date
        FROM read_parquet('{parquet_pattern}')
        GROUP BY symbol
    )
""").fetchone()

most_recent = result[0]
oldest_latest = result[1]
total_symbols = result[2]

days_ago = (today - most_recent).days
print(f"Most Recent Data: {most_recent} ({days_ago} days ago)")
print(f"Oldest Latest Date: {oldest_latest}")
print(f"Total Symbols: {total_symbols}")

# Distribution of freshness
result = conn.execute(f"""
    SELECT
        CASE
            WHEN DATEDIFF('day', latest_date, CURRENT_DATE) = 0 THEN 'Today'
            WHEN DATEDIFF('day', latest_date, CURRENT_DATE) = 1 THEN '1 day ago'
            WHEN DATEDIFF('day', latest_date, CURRENT_DATE) <= 3 THEN '2-3 days ago'
            WHEN DATEDIFF('day', latest_date, CURRENT_DATE) <= 7 THEN '4-7 days ago'
            WHEN DATEDIFF('day', latest_date, CURRENT_DATE) <= 30 THEN '1-4 weeks ago'
            ELSE '> 1 month ago'
        END as freshness,
        COUNT(*) as symbol_count
    FROM (
        SELECT symbol, MAX(timestamp)::DATE as latest_date
        FROM read_parquet('{parquet_pattern}')
        GROUP BY symbol
    )
    GROUP BY freshness
    ORDER BY MIN(DATEDIFF('day', latest_date, CURRENT_DATE))
""").fetchall()

print("\nFreshness Distribution:")
for row in result:
    print(f"  {row[0]:20} {row[1]:5} symbols")

# 2. Completeness - Trading days coverage
print("\n📊 COMPLETENESS BY TIME PERIOD")
print("-" * 80)

# Check last 30 days completeness
result = conn.execute(f"""
    WITH recent_data AS (
        SELECT
            symbol,
            COUNT(DISTINCT DATE_TRUNC('day', timestamp)) as actual_days
        FROM read_parquet('{parquet_pattern}')
        WHERE timestamp >= CURRENT_DATE - INTERVAL 30 DAY
        GROUP BY symbol
    )
    SELECT
        CASE
            WHEN actual_days >= 20 THEN 'Excellent (20+ days)'
            WHEN actual_days >= 15 THEN 'Good (15-19 days)'
            WHEN actual_days >= 10 THEN 'Fair (10-14 days)'
            WHEN actual_days >= 5 THEN 'Poor (5-9 days)'
            ELSE 'Very Poor (<5 days)'
        END as completeness,
        COUNT(*) as symbol_count
    FROM recent_data
    GROUP BY completeness
    ORDER BY MIN(actual_days) DESC
""").fetchall()

print("Last 30 Days Coverage:")
for row in result:
    print(f"  {row[0]:25} {row[1]:5} symbols")

# 3. Missing recent data
print("\n⚠️  SYMBOLS MISSING RECENT DATA (>7 days old)")
print("-" * 80)

result = conn.execute(f"""
    SELECT
        symbol,
        MAX(timestamp)::DATE as latest_date,
        DATEDIFF('day', MAX(timestamp)::DATE, CURRENT_DATE) as days_old
    FROM read_parquet('{parquet_pattern}')
    GROUP BY symbol
    HAVING MAX(timestamp) < CURRENT_DATE - INTERVAL 7 DAY
    ORDER BY days_old DESC
    LIMIT 20
""").fetchall()

if result:
    print(f"{'Symbol':<15} {'Latest Date':>12} {'Days Old':>10}")
    print("-" * 40)
    for row in result:
        print(f"{row[0]:<15} {row[1]!s:>12} {row[2]:>10}")
else:
    print("✓ All symbols have recent data (within 7 days)")

# 4. Intraday completeness (sample)
print("\n⏰ INTRADAY COMPLETENESS (Sample: Last Trading Day)")
print("-" * 80)

# Get the most recent trading day
result = conn.execute(f"""
    SELECT MAX(timestamp)::DATE as trading_date
    FROM read_parquet('{parquet_pattern}')
""").fetchone()

trading_date = result[0]
print(f"Analyzing: {trading_date}")

# Check a sample of symbols
result = conn.execute(f"""
    SELECT
        symbol,
        COUNT(*) as candles,
        MIN(timestamp) as first_candle,
        MAX(timestamp) as last_candle
    FROM read_parquet('{parquet_pattern}')
    WHERE timestamp::DATE = '{trading_date}'
    GROUP BY symbol
    ORDER BY candles DESC
    LIMIT 10
""").fetchall()

print(f"{'Symbol':<15} {'Candles':>10} {'First':>10} {'Last':>10} {'Expected':>10}")
print("-" * 60)
for row in result:
    candles = row[1]
    # Expected ~375 candles for full day (9:15 to 15:30)
    expected = 375
    pct = (candles / expected * 100) if expected > 0 else 0
    print(
        f"{row[0]:<15} {candles:>10,} {str(row[2])[11:16]:>10} {str(row[3])[11:16]:>10} {expected:>10} ({pct:.0f}%)"
    )

# 5. Zero volume analysis
print("\n📉 ZERO VOLUME ANALYSIS")
print("-" * 80)

result = conn.execute(f"""
    SELECT
        CASE
            WHEN zero_pct = 0 THEN '0% (Perfect)'
            WHEN zero_pct < 1 THEN '<1%'
            WHEN zero_pct < 5 THEN '1-5%'
            WHEN zero_pct < 10 THEN '5-10%'
            ELSE '>10%'
        END as zero_volume_rate,
        COUNT(*) as symbol_count
    FROM (
        SELECT
            symbol,
            ROUND(SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as zero_pct
        FROM read_parquet('{parquet_pattern}')
        GROUP BY symbol
    )
    GROUP BY zero_volume_rate
    ORDER BY MIN(CASE
        WHEN zero_pct = 0 THEN 0
        WHEN zero_pct < 1 THEN 1
        WHEN zero_pct < 5 THEN 2
        WHEN zero_pct < 10 THEN 3
        ELSE 4
    END)
""").fetchall()

print("Zero Volume Distribution:")
for row in result:
    print(f"  {row[0]:20} {row[1]:5} symbols")

# Top symbols with most zero volume
result = conn.execute(f"""
    SELECT
        symbol,
        COUNT(*) as total,
        SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) as zero_vol,
        ROUND(SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as zero_pct
    FROM read_parquet('{parquet_pattern}')
    GROUP BY symbol
    HAVING zero_vol > 100
    ORDER BY zero_vol DESC
    LIMIT 10
""").fetchall()

print("\nTop 10 Symbols with Most Zero Volume Bars:")
print(f"{'Symbol':<15} {'Total':>10} {'Zero Vol':>10} {'Pct':>8}")
print("-" * 50)
for row in result:
    print(f"{row[0]:<15} {row[1]:>10,} {row[2]:>10,} {row[3]:>7}%")

print("\n" + "=" * 80)
print("REPORT COMPLETE")
print("=" * 80)

conn.close()
