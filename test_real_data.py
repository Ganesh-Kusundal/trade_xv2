#!/usr/bin/env python3
"""Test real historical data retrieval from Dhan."""
import asyncio
import time
import sys

sys.path.insert(0, '/workspace')

from brokers.dhan.factory import BrokerFactory
from domain.entities.instrument import Instrument


async def main():
    print('🔍 Testing REAL Historical Data from Dhan Gateway...')
    print('=' * 60)

    try:
        # Use Factory Pattern - load instruments is required for history lookups
        print('⏳ Creating gateway via BrokerFactory (loading instruments)...')
        factory = BrokerFactory()
        gateway = factory.create(load_instruments=True)  # Must load instruments for history
        print('✅ Gateway created successfully')

        # Test instrument: RELIANCE equity (symbol will be resolved by gateway)
        print(f'\n📡 Fetching 1-minute historical data for RELIANCE...')
        start_time = time.time()

        # Fetch last 2 days of 1-minute data - using correct method signature
        bars = gateway.history(
            symbol='RELIANCE',
            exchange='NSE',
            timeframe='1min',
            lookback_days=2
        )

        elapsed = time.time() - start_time
        print(f'⏱️  Retrieved in {elapsed:.2f} seconds')

        if not bars:
            print('❌ ERROR: No data returned')
            return False

        print(f'✅ SUCCESS: Retrieved {len(bars)} bars')

        # Verify data quality
        print('\n📊 DATA VERIFICATION:')
        print('-' * 60)

        first_bar = bars[0]
        last_bar = bars[-1]

        print(f'First Bar: {first_bar.get("timestamp")} | O:{first_bar.get("open")} H:{first_bar.get("high")} L:{first_bar.get("low")} C:{first_bar.get("close")} V:{first_bar.get("volume")}')
        print(f'Last Bar:  {last_bar.get("timestamp")} | O:{last_bar.get("open")} H:{last_bar.get("high")} L:{last_bar.get("low")} C:{last_bar.get("close")} V:{last_bar.get("volume")}')

        # Validate integrity
        print('\n🔍 INTEGRITY CHECKS:')
        avg_close = sum(bar['close'] for bar in bars) / len(bars)
        print(f'Average Close: ₹{avg_close:.2f}')
        
        volumes = [bar['volume'] for bar in bars]
        avg_volume = sum(volumes) / len(volumes)
        print(f'Average Volume: {avg_volume:.0f}')

        # OHLC check
        invalid = sum(1 for b in bars if not (b['high'] >= b['low'] and b['high'] >= max(b['open'], b['close']) and b['low'] <= min(b['open'], b['close'])))
        print(f'Invalid OHLC bars: {invalid}')

        # Timestamp order
        timestamps = [b['timestamp'] for b in bars]
        is_sorted = all(timestamps[i] < timestamps[i+1] for i in range(len(timestamps)-1))
        print(f'Timestamps ordered: {is_sorted}')

        print('\n' + '=' * 60)
        print('🎉 REAL DATA SUCCESSFULLY RETRIEVED FROM DHAN')
        print('=' * 60)
        return True

    except Exception as e:
        print(f'❌ ERROR: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
