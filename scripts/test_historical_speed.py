#!/usr/bin/env python3
"""Historical data retrieval speed test for Dhan broker."""
import time
import sys
sys.path.insert(0, '/workspace')

from brokers.dhan.factory import BrokerFactory
from domain.entities.instrument import Instrument
from decimal import Decimal

def main():
    print('=== HISTORICAL DATA RETRIEVAL SPEED TEST ===\n')
    
    # Use same factory pattern as test_broker_connection.py (which works)
    factory = BrokerFactory()
    
    print('Initializing gateway (this may take time due to instrument loading)...')
    start_init = time.time()
    gateway = factory.create()
    init_time = time.time() - start_init
    print(f'Gateway initialized in {init_time:.2f}s\n')
    
    # Test Case 1: NIFTY Futures
    print('Test 1: NIFTY Futures (1-minute bars, Last 5 days)')
    instrument_nifty = Instrument(
        symbol='NIFTY24JULFUT',
        exchange='NSE',
        security_id='13000',
        instrument_type='FUT',
        lot_size=25
    )
    
    start = time.time()
    bars_nifty = gateway.get_historical_bars(
        instrument=instrument_nifty,
        interval='1m',
        days=5
    )
    elapsed_nifty = time.time() - start
    
    print(f'  Bars retrieved: {len(bars_nifty)}')
    print(f'  Time taken: {elapsed_nifty:.3f}s')
    if bars_nifty and elapsed_nifty > 0:
        print(f'  Speed: {len(bars_nifty)/elapsed_nifty:.1f} bars/sec')
        if bars_nifty:
            print(f'  First bar: {bars_nifty[0].timestamp}')
            print(f'  Last bar: {bars_nifty[-1].timestamp}')
    print()
    
    # Test Case 2: BANKNIFTY Futures
    print('Test 2: BANKNIFTY Futures (5-minute bars, Last 10 days)')
    instrument_bank = Instrument(
        symbol='BANKNIFTY24JULFUT',
        exchange='NSE',
        security_id='13001',
        instrument_type='FUT',
        lot_size=15
    )
    
    start = time.time()
    bars_bank = gateway.get_historical_bars(
        instrument=instrument_bank,
        interval='5m',
        days=10
    )
    elapsed_bank = time.time() - start
    
    print(f'  Bars retrieved: {len(bars_bank)}')
    print(f'  Time taken: {elapsed_bank:.3f}s')
    if bars_bank and elapsed_bank > 0:
        print(f'  Speed: {len(bars_bank)/elapsed_bank:.1f} bars/sec')
    print()
    
    print('=== PERFORMANCE SUMMARY ===')
    avg_time = (elapsed_nifty + elapsed_bank) / 2
    print(f'Average retrieval time: {avg_time:.3f}s')
    if avg_time < 2.0:
        print('✅ PASS: Latency acceptable for live trading (< 2s)')
    else:
        print('⚠️ WARNING: Latency high, consider caching for backtesting')

if __name__ == '__main__':
    main()
