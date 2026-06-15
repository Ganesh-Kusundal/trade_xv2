# Upstox Fix Plan

**Created:** 2026-06-13
**Priority:** CRITICAL

---

## Critical Issue 1: V2 Historical Candle Deprecated

### Root Cause
Our implementation uses `/v2/historical-candle` which is deprecated.

### Current Implementation
```python
# brokers/upstox/market_data/historical_v2.py
url = self._urls.historical_candle_url()  # Returns V2 URL
```

### Required Fix
Migrate to V3 endpoint:
```python
# V3 format: /v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}
url = f"https://api.upstox.com/v3/historical-candle/{key}/{unit}/{interval}/{to_date}/{from_date}"
```

### Impact
- HIGH: V2 may stop working without notice
- V3 supports all intervals (1m-300m, 1h-5h, 1D, 1W, 1M)

---

## Critical Issue 2: V2 Intervals Limited

### Root Cause
V2 only supports: `1minute`, `30minute`, `day`, `week`, `month`

### Current Implementation
```python
# brokers/upstox/gateway.py
interval_map = {"1": "1minute", "5": "1minute", ...}  # Maps 5m to 1m!
```

### Required Fix
Use V3 with proper intervals:
```python
# V3 format: minutes/1, minutes/5, minutes/15, hours/1, days/1, etc.
interval_map = {
    "1": ("minutes", "1"),
    "3": ("minutes", "3"),
    "5": ("minutes", "5"),
    "15": ("minutes", "15"),
    "30": ("minutes", "30"),
    "60": ("hours", "1"),
    "1D": ("days", "1"),
    "1W": ("weeks", "1"),
    "1M": ("months", "1"),
}
```

---

## Critical Issue 3: Order Book Deprecated

### Root Cause
`/v2/market-quote/order-book` returns 400.

### Current Implementation
```python
# brokers/upstox/gateway.py
def get_depth(self, symbol, exchange):
    body = self._broker.market_data_v2.get_order_book(key)  # Fails
```

### Required Fix
Option 1: Remove depth support for Upstox
Option 2: Use alternative endpoint if available

### Impact
MEDIUM: Depth not available for Upstox

---

## Critical Issue 4: Option Expiry Deprecated

### Root Cause
`/v2/option/expiry` returns 400.

### Current Implementation
```python
# brokers/upstox/gateway.py
expiries = self._broker.options.get_expiries(underlying, segment)  # Fails
```

### Required Fix
Option 1: Remove option chain support for Upstox
Option 2: Use alternative endpoint if available

### Impact
MEDIUM: Option chain not available for Upstox

---

## Implementation Order

1. **T37**: Fix V2 → V3 migration for historical candles
2. **T38**: Update interval mapping for V3
3. **T39**: Remove/update depth support
4. **T40**: Remove/update option chain support
5. **T41**: Update verified capabilities document
6. **T42**: Run full test suite

---

## Verification Checklist

After fixes:
- [ ] V3 historical candles work for all intervals
- [ ] V3 interval mapping correct
- [ ] Depth gracefully handled (removed or alternative)
- [ ] Option chain gracefully handled (removed or alternative)
- [ ] All tests pass
- [ ] Verified capabilities document updated
