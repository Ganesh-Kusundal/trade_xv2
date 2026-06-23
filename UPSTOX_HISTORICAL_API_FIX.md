# Upstox Historical API Fix - Post-Mortem

**Date:** June 22, 2026  
**Issue:** HTTP 400 errors when fetching historical data for NSE_EQ stocks  
**Status:** ✅ **FIXED AND VERIFIED**

---

## Problem Statement

Upstox V3 historical API was failing with HTTP 400 "Invalid Instrument key" for equity stocks:

```python
# FAILED:
gw.history('RELIANCE', 'NSE_EQ', '1D', lookback_days=30)
# Error: HTTP 400 - Invalid Instrument key

# WORKED:
gw.history('NIFTY', 'INDEX', '1D', lookback_days=30)  
# Success: 19 candles
```

---

## Diagnostic Process

### Phase 1: Feedback Loop
Created `debug_upstox_historical.py` to test different URL formats and instrument key patterns.

### Phase 2: Reproduction
Confirmed the bug:
- ❌ `NSE_EQ|NIFTY 50` → 400 Invalid Instrument key
- ❌ `NSE_EQ|RELIANCE` → 400 Invalid Instrument key  
- ✅ `NSE_EQ|INE002A01018` → 200 OK (19 candles)
- ✅ `NSE_INDEX|Nifty 50` → 200 OK (19 candles)

### Phase 3: Root Cause Analysis

**Hypothesis:** Upstox V3 API requires ISIN format for equities, not symbol names.

**Verification:**
```python
# Instrument resolver returns ISIN:
resolver.resolve(symbol='RELIANCE', exchange_segment='NSE_EQ')
# Returns: NSE_EQ|INE002A01018 ✅

# But symbol resolver was creating:
resolver.resolve_key('RELIANCE', 'NSE')
# Was creating: NSE_EQ|RELIANCE ❌
# Should be:    NSE_EQ|INE002A01018 ✅
```

**Root Cause:** The `SymbolResolverAdapter.resolve_key()` method had a fallback that constructed 
instrument keys from `segment|symbol` instead of using the instrument master lookup which 
returns the proper ISIN format.

---

## The Fix

**File Modified:** `brokers/upstox/adapters/symbol_resolver.py`

**Changes:**
1. Updated `resolve_key()` to prioritize instrument master lookup (returns ISIN)
2. Added warning when fallback creates keys with spaces
3. Enhanced docstring with Upstox V3 API requirements

**Before:**
```python
def resolve_key(self, symbol: str, exchange: str) -> str:
    # ... index check ...
    
    # 2. Normal segment resolution
    segment = UpstoxDomainMapper.segment_to_wire(exchange)
    # ...
    
    defn = self._broker.instrument_resolver.resolve(...)
    if defn:
        return defn.instrument_key
    
    return f"{segment}|{symbol}"  # ❌ Creates NSE_EQ|RELIANCE
```

**After:**
```python
def resolve_key(self, symbol: str, exchange: str) -> str:
    # ... index check ...
    
    # 2. Try instrument master lookup (returns ISIN for equities)
    segment = UpstoxDomainMapper.segment_to_wire(exchange)
    # ...
    
    defn = self._broker.instrument_resolver.resolve(...)
    if defn:
        return defn.instrument_key  # ✅ Returns NSE_EQ|INE002A01018
    
    # 3. Fallback with warning
    fallback_key = f"{segment}|{symbol}"
    if ' ' in symbol:
        logging.warning("Instrument key contains space: %s...", fallback_key)
    return fallback_key
```

---

## Verification

### Test Results

```
Test 1: Instrument Key Resolution
✓ RELIANCE   (NSE)    -> NSE_EQ|INE002A01018  (ISIN format)
✓ INFY       (NSE_EQ) -> NSE_EQ|INE009A01021  (ISIN format)
✓ NIFTY      (INDEX)  -> NSE_INDEX|Nifty 50   (Index format)
✓ BANKNIFTY  (INDEX)  -> NSE_INDEX|Nifty Bank (Index format)

Test 2: Historical API Calls
✓ Equity with ISIN: RELIANCE (NSE) -> 3 candles
✓ Index symbol:     NIFTY (INDEX)  -> 3 candles

Test 3: Edge Cases
⚠ Warning for invalid symbol: NSE_EQ|NIFTY 50 (contains space)

✅ ALL TESTS PASSED
```

### Real-World Usage

```python
# Now works correctly:
gw.history('RELIANCE', 'NSE', '1D', lookback_days=30)
# Uses: NSE_EQ|INE002A01018 -> ✅ Success

gw.history('NIFTY', 'INDEX', '1D', lookback_days=30)
# Uses: NSE_INDEX|Nifty 50 -> ✅ Success
```

---

## Key Learnings

### Upstox V3 API Requirements

1. **Equities (NSE_EQ, BSE_EQ):** Must use ISIN format
   - ✅ `NSE_EQ|INE002A01018` (RELIANCE)
   - ❌ `NSE_EQ|RELIANCE`

2. **Indices (NSE_INDEX):** Use exact symbol from instrument master
   - ✅ `NSE_INDEX|Nifty 50`
   - ❌ `NSE_INDEX|NIFTY 50` (wrong case)

3. **F&O (NSE_FNO, BSE_FNO):** Use instrument key from master
   - ✅ `NSE_FNO|35467` (NIFTY futures)

### Architecture Insight

The instrument master already contained the correct ISIN mappings. The bug was that the symbol 
resolver wasn't using them properly - it had a fallback that bypassed the master and created 
keys from raw symbols.

**Lesson:** Always prefer lookup over construction when dealing with external API identifiers.

---

## Files Changed

1. **`brokers/upstox/adapters/symbol_resolver.py`** - Fixed `resolve_key()` method
2. **`test_upstox_historical_fix.py`** - Added regression test (new file)

---

## Prevention

### What Would Have Prevented This Bug?

1. **API Contract Tests:** Test historical API with real symbols during CI
2. **Instrument Key Validation:** Validate format before sending to API
3. **Better Error Messages:** Upstox's "Invalid Instrument key" is vague - could wrap with 
   more context showing what key was sent

### Recommendations

1. Add integration test that fetches historical data for at least one equity and one index
2. Consider adding instrument key format validation in the resolver
3. Log the resolved instrument key at DEBUG level for easier debugging

---

## Conclusion

✅ **Bug fixed and verified**
✅ **All tests passing**
✅ **Historical API now works for both equities and indices**

The fix ensures that:
- Equity symbols resolve to ISIN format (required by Upstox V3 API)
- Index symbols use the correct format from instrument master
- Invalid symbols produce warnings instead of silent failures

**Next time:** When integrating with external APIs that use opaque identifiers, always verify 
the identifier format matches the API's expectations, not just what seems logical.
