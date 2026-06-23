"""Quick data quality analysis using DuckDB."""

import duckdb
from pathlib import Path

# Connect to catalog
conn = duckdb.connect('market_data/catalog.duckdb')

# Get overview
print("=" * 80)
print("INDIAN STOCKS DATA QUALITY REPORT")
print("=" * 80)

# 1. Basic Statistics
print("\n📊 BASIC STATISTICS")
print("-" * 80)
result = conn.execute("""
    SELECT 
        COUNT(*) as total_symbols,
        SUM(total_rows) as total_candles,
        MIN(first_date) as earliest_date,
        MAX(last_date) as latest_date
    FROM symbols
""").fetchone()
print(f"Total Symbols: {result[0]:,}")
print(f"Total Candles: {result[1]:,}")
print(f"Date Range: {result[2]} to {result[3]}")

# 2. Date Range Distribution
print("\n📅 DATE RANGE DISTRIBUTION")
print("-" * 80)
result = conn.execute("""
    SELECT 
        CASE 
            WHEN DATEDIFF('day', first_date, last_date) < 30 THEN '< 1 month'
            WHEN DATEDIFF('day', first_date, last_date) < 90 THEN '1-3 months'
            WHEN DATEDIFF('day', first_date, last_date) < 180 THEN '3-6 months'
            WHEN DATEDIFF('day', first_date, last_date) < 365 THEN '6-12 months'
            ELSE '> 1 year'
        END as range_category,
        COUNT(*) as symbol_count,
        MIN(DATEDIFF('day', first_date, last_date)) as min_days,
        MAX(DATEDIFF('day', first_date, last_date)) as max_days
    FROM symbols
    GROUP BY range_category
    ORDER BY min_days
""").fetchall()

for row in result:
    print(f"{row[0]:15} {row[1]:5} symbols  ({row[2]}-{row[3]} days)")

# 3. Data Volume Distribution
print("\n📦 DATA VOLUME DISTRIBUTION")
print("-" * 80)
result = conn.execute("""
    SELECT 
        CASE 
            WHEN total_rows < 10000 THEN '< 10K candles'
            WHEN total_rows < 50000 THEN '10K-50K'
            WHEN total_rows < 100000 THEN '50K-100K'
            WHEN total_rows < 500000 THEN '100K-500K'
            ELSE '> 500K candles'
        END as volume_category,
        COUNT(*) as symbol_count,
        SUM(total_rows) as total_candles
    FROM symbols
    GROUP BY volume_category
    ORDER BY SUM(total_rows)
""").fetchall()

for row in result:
    print(f"{row[0]:20} {row[1]:5} symbols  {row[2]:>12,} candles")

# 4. Quality Issues
print("\n⚠️  DATA QUALITY ISSUES")
print("-" * 80)

# Check for zero volume
result = conn.execute("""
    SELECT COUNT(*) FROM symbols WHERE total_rows = 0
""").fetchone()
print(f"Symbols with no data: {result[0]}")

# 5. Sample Quality Report from DuckDB Views
print("\n🔍 SAMPLE DATA QUALITY (Top 20 by Volume)")
print("-" * 80)

parquet_dir = Path('market_data/equities/candles/timeframe=1m')
if parquet_dir.exists():
    parquet_pattern = str(parquet_dir / 'symbol=*' / 'data.parquet')
    
    result = conn.execute(f"""
        SELECT 
            symbol,
            COUNT(*) as total_candles,
            MIN(timestamp)::DATE as first_date,
            MAX(timestamp)::DATE as last_date,
            COUNT(DISTINCT DATE_TRUNC('day', timestamp)) as trading_days,
            SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) as zero_volume,
            SUM(CASE WHEN high < low THEN 1 ELSE 0 END) as ohlc_errors,
            ROUND(AVG(high - low), 2) as avg_range
        FROM read_parquet('{parquet_pattern}')
        GROUP BY symbol
        ORDER BY total_candles DESC
        LIMIT 20
    """).fetchall()
    
    print(f"{'Symbol':<15} {'Candles':>10} {'Days':>6} {'First':>12} {'Last':>12} {'Zero Vol':>10} {'OHLC Err':>10}")
    print("-" * 80)
    for row in result:
        symbol, candles, first, last, days, zero_vol, ohlc_err, avg_range = row
        print(f"{symbol:<15} {candles:>10,} {days:>6} {str(first):>12} {str(last):>12} {zero_vol:>10,} {ohlc_err:>10}")
    
    # 6. Quality Summary Statistics
    print("\n📈 OVERALL QUALITY METRICS")
    print("-" * 80)
    
    result = conn.execute(f"""
        SELECT 
            COUNT(DISTINCT symbol) as total_symbols,
            SUM(CASE WHEN zero_volume > 0 THEN 1 ELSE 0 END) as symbols_with_zero_vol,
            SUM(CASE WHEN ohlc_errors > 0 THEN 1 ELSE 0 END) as symbols_with_ohlc_errors,
            AVG(trading_days) as avg_trading_days,
            SUM(total_candles) as total_candles
        FROM (
            SELECT 
                symbol,
                COUNT(*) as total_candles,
                COUNT(DISTINCT DATE_TRUNC('day', timestamp)) as trading_days,
                SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) as zero_volume,
                SUM(CASE WHEN high < low THEN 1 ELSE 0 END) as ohlc_errors
            FROM read_parquet('{parquet_pattern}')
            GROUP BY symbol
        )
    """).fetchone()
    
    total_symbols = result[0]
    zero_vol_symbols = result[1]
    ohlc_error_symbols = result[2]
    avg_days = result[3]
    total_candles = result[4]
    
    print(f"Total Symbols Analyzed: {total_symbols:,}")
    print(f"Total Candles: {total_candles:,}")
    print(f"Avg Trading Days per Symbol: {avg_days:.0f}")
    print(f"Symbols with Zero Volume Issues: {zero_vol_symbols} ({zero_vol_symbols/total_symbols*100:.1f}%)")
    print(f"Symbols with OHLC Errors: {ohlc_error_symbols} ({ohlc_error_symbols/total_symbols*100:.1f}%)")
    
    # 7. Symbols with Most Issues
    print("\n🚨 SYMBOLS WITH MOST DATA QUALITY ISSUES")
    print("-" * 80)
    
    result = conn.execute(f"""
        SELECT 
            symbol,
            total_candles,
            zero_volume,
            ohlc_errors,
            trading_days
        FROM (
            SELECT 
                symbol,
                COUNT(*) as total_candles,
                COUNT(DISTINCT DATE_TRUNC('day', timestamp)) as trading_days,
                SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) as zero_volume,
                SUM(CASE WHEN high < low THEN 1 ELSE 0 END) as ohlc_errors
            FROM read_parquet('{parquet_pattern}')
            GROUP BY symbol
        )
        WHERE zero_volume > 100 OR ohlc_errors > 0
        ORDER BY zero_volume DESC, ohlc_errors DESC
        LIMIT 20
    """).fetchall()
    
    if result:
        print(f"{'Symbol':<15} {'Candles':>10} {'Days':>6} {'Zero Vol':>10} {'OHLC Err':>10}")
        print("-" * 80)
        for row in result:
            symbol, candles, days, zero_vol, ohlc_err = row
            print(f"{symbol:<15} {candles:>10,} {days:>6} {zero_vol:>10,} {ohlc_err:>10}")
    else:
        print("✓ No symbols with significant quality issues found!")

else:
    print("Parquet files not found for detailed analysis")

print("\n" + "=" * 80)
print("REPORT COMPLETE")
print("=" * 80)

conn.close()
