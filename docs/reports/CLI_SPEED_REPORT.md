# CLI Speed Test Report

## Current Performance (Before Cache Optimization)

| Metric | Time | Status |
|--------|------|--------|
| Import time | 1.4-3.2s | ⚠️ Slow (importing many modules) |
| Initialization | 27-37s | ❌ Too slow (loading 234k instruments) |
| First quote | 1.1-1.3s | ⚠️ Slow (token expired) |
| **Total** | **30-42s** | ❌ **Unacceptable** |

## Root Cause Analysis

### Problem 1: SQLite Cache Not Being Populated
- The `load_instruments()` method loads instruments into **in-memory resolver only**
- SQLite cache remains **empty** (0 instruments in `instruments_dhan` table)
- Every CLI invocation reloads all 234,825 instruments from CSV (11s load + conversion)

### Problem 2: Lazy Refresh Blocking Initialization
- When cache is expired/empty, lazy refresh triggers during `_ensure_initialized()`
- This blocks the entire CLI startup for 27-37s
- Lazy refresh should happen **asynchronously** or **after** initialization

### Problem 3: Cache Metadata Issue
- Test script tried to read `cached_at` column but schema uses `last_refresh`
- Cache metadata table exists but shows empty in queries

## What's Working ✅

1. **Symbol resolution interceptor** - Code is integrated into gateways
2. **Performance benchmarks** - SQLite queries are fast (375ns vs 10ms target)
3. **Lazy refresh logic** - Thread-safe double-checked locking works
4. **Test suite** - All 835 tests passing

## What Needs Fixing ❌

1. **Populate SQLite cache during `load_instruments()`**
   - After loading into in-memory resolver, also cache to SQLite
   - This ensures subsequent CLI invocations use fast SQLite path

2. **Make lazy refresh non-blocking**
   - Return stale data immediately, refresh in background
   - Or defer refresh until first actual symbol resolution

3. **Fix Dhan factory loader**
   - Changed to return dicts instead of Instrument objects ✅
   - But loader isn't being called during initialization

## Recommended Fix

Modify `DhanConnection.load_instruments()` to populate SQLite cache:

```python
def load_instruments(self, source: Optional[str] = None, use_cache: bool = True) -> None:
    # Load instruments (existing logic)
    if source is not None:
        # ... existing code ...
    elif use_cache:
        rows = InstrumentLoader.load_cached()
    else:
        rows = InstrumentLoader.load_cached(force_refresh=True)
    
    # Load into in-memory resolver (existing)
    self.instruments.load_from_rows(rows)
    
    # NEW: Also populate SQLite cache for fast subsequent lookups
    if hasattr(self, 'instrument_cache') and self.instrument_cache:
        self.instrument_cache.cache_instruments('dhan', rows)
```

## Expected Performance After Fix

| Scenario | Current | Expected | Improvement |
|----------|---------|----------|-------------|
| Cold start (1st run) | 37s | 12s | 3x faster |
| Warm start (2nd+ run) | 37s | **< 2s** | **18x faster** |
| Symbol resolution | ~10ms | **< 1μs** | **10,000x faster** |
| Batch (100 symbols) | ~1s | **< 50ms** | **20x faster** |

## Next Steps

1. ✅ Fix Dhan factory loader (done - returns dicts)
2. ❌ Populate SQLite cache during `load_instruments()`
3. ❌ Test warm start performance
4. ❌ Verify symbol resolution uses SQLite cache
5. ❌ Measure end-to-end CLI speed improvement
