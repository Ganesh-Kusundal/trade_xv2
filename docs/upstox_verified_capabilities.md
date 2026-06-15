# Upstox Verified Capabilities

**Last Verified:** 2026-06-13
**Source:** Official Upstox API Documentation (https://upstox.com/developer/api-documentation/)

---

## Historical Data

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Historical Candle (1m-30m) | `/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}` | V3 | ✅ VERIFIED | 2026-06-13 |
| Historical Candle (1D-1M) | `/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}` | V3 | ✅ VERIFIED | 2026-06-13 |
| Intraday Candle | `/v3/intraday-candle/{key}/{unit}/{interval}/{to}` | V3 | ✅ VERIFIED | 2026-06-13 |
| Historical Candle V2 | `/v2/historical-candle/{key}/{interval}/{to}/{from}` | V2 | ⚠️ DEPRECATED | 2026-06-13 |

### V3 Intervals Verified

| Unit | Interval | Status | Candles (11 days) |
|------|----------|--------|-------------------|
| minutes | 1 | ✅ | 3375 |
| minutes | 3 | ✅ | 1250 |
| minutes | 5 | ✅ | 675 |
| minutes | 15 | ✅ | 225 |
| minutes | 30 | ✅ | 130 |
| hours | 1 | ✅ | 70 |
| hours | 4 | ✅ | 20 |
| days | 1 | ✅ | 10 |
| weeks | 1 | ✅ | 2 |
| months | 1 | ✅ | 1 |

### V2 Intervals (Deprecated)

| Interval | Status | Notes |
|----------|--------|-------|
| 1minute | ✅ Works | Deprecated |
| 30minute | ✅ Works | Deprecated |
| day | ✅ Works | Deprecated |
| week | ✅ Works | Deprecated |
| month | ✅ Works | Deprecated |
| 5minute | ❌ | Not supported in V2 |
| 15minute | ❌ | Not supported in V2 |
| 60minute | ❌ | Not supported in V2 |

---

## Market Data

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| LTP | `/v2/market-quote/ltp` | V2 | ✅ VERIFIED | 2026-06-13 |
| Quote | `/v2/market-quote/quotes` | V2 | ✅ VERIFIED | 2026-06-13 |
| OHLC | `/v2/market-quote/ohlc` | V2 | ✅ VERIFIED | 2026-06-13 |
| Order Book (Depth) | `/v2/market-quote/order-book` | V2 | ❌ DEPRECATED | 2026-06-13 |
| Full Quote | `/v3/market-quote/full` | V3 | ❌ NOT FOUND | 2026-06-13 |
| LTP V3 | `/v3/market-quote/ltp` | V3 | ✅ VERIFIED | 2026-06-13 |
| Option Greeks V3 | `/v3/market-quote/option-greeks` | V3 | ❌ NOT FOUND | 2026-06-13 |

---

## Option Chain

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Option Chain | `/v2/option/chain` | V2 | ✅ VERIFIED | 2026-06-13 |
| Option Expiry | `/v2/option/expiry` | V2 | ❌ DEPRECATED | 2026-06-13 |
| Option Contracts | `/v2/option/contracts` | V2 | ❌ NOT FOUND | 2026-06-13 |
| Option Greeks | `/v2/option/greeks` | V2 | ❌ NOT FOUND | 2026-06-13 |

---

## Portfolio

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Positions | `/v2/portfolio/short-term-positions` | V2 | ✅ VERIFIED | 2026-06-13 |
| Holdings | `/v2/portfolio/long-term-holdings` | V2 | ✅ VERIFIED | 2026-06-13 |
| Funds | `/v2/user/get-funds-and-margin` | V2 | ✅ VERIFIED | 2026-06-13 |
| Profile | `/v2/user/profile` | V2 | ✅ VERIFIED | 2026-06-13 |
| MTF Positions | `/v3/portfolio/mtf-positions` | V3 | ❌ NOT FOUND | 2026-06-13 |

---

## Orders

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Place Order | `/v2/order/place` | V2 | ✅ VERIFIED | 2026-06-13 |
| Modify Order | `/v2/order/modify` | V2 | ✅ VERIFIED | 2026-06-13 |
| Cancel Order | `/v2/order/cancel` | V2 | ✅ VERIFIED | 2026-06-13 |
| Order History | `/v2/order/history` | V2 | ✅ VERIFIED | 2026-06-13 |
| Order Details | `/v3/order/details` | V3 | ❌ NOT FOUND | 2026-06-13 |
| Order History V3 | `/v3/order/history` | V3 | ❌ NOT FOUND | 2026-06-13 |
| Trades | `/v2/order/trades` | V2 | ✅ VERIFIED | 2026-06-13 |
| Trades V3 | `/v3/order/trades/get-trades-for-day` | V3 | ❌ NOT FOUND | 2026-06-13 |

---

## WebSocket

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Market Data Feed | `/v3/feed/market-data-feed/authorize` | V3 | ✅ VERIFIED | 2026-06-13 |
| Portfolio Stream | `/v2/feed/portfolio-stream-feed/authorize` | V2 | ✅ VERIFIED | 2026-06-13 |
| Market Data Feed V2 | `/v2/feed/market-data-feed/authorize` | V2 | ❌ DEPRECATED (410) | 2026-06-13 |

---

## Market Information

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Market Status | `/v2/market/status/{segment}` | V2 | ✅ VERIFIED | 2026-06-13 |
| Holidays | `/v2/market/holidays` | V2 | ✅ VERIFIED | 2026-06-13 |
| PCR | `/v2/market/pcr` | V2 | ✅ VERIFIED | 2026-06-13 |
| OI | `/v2/market/oi` | V2 | ✅ VERIFIED | 2026-06-13 |
| Max Pain | `/v2/market/max-pain` | V2 | ✅ VERIFIED | 2026-06-13 |
| FII | `/v2/market/fii` | V2 | ✅ VERIFIED | 2026-06-13 |
| DII | `/v2/market/dii` | V2 | ✅ VERIFIED | 2026-06-13 |

---

## Account

| Feature | Endpoint | Version | Status | Verified Date |
|---------|----------|---------|--------|---------------|
| Kill Switch | `/v2/user/kill-switch` | V2 | ✅ VERIFIED | 2026-06-13 |
| Static IP | `/v2/user/ip` | V2 | ✅ VERIFIED | 2026-06-13 |

---

## Deprecated Endpoints Still in Use

| Endpoint | Status | Replacement | Risk |
|----------|--------|-------------|------|
| `/v2/historical-candle` | DEPRECATED | `/v3/historical-candle` | HIGH |
| `/v2/market-quote/order-book` | DEPRECATED | None available | MEDIUM |
| `/v2/option/expiry` | DEPRECATED | None available | MEDIUM |
| `/v2/feed/market-data-feed/authorize` | DEPRECATED (410) | `/v3/feed/market-data-feed/authorize` | LOW |

---

## Rate Limits (Verified)

| Endpoint Category | Limit | Source |
|-------------------|-------|--------|
| Market Data | 100 req/s | Official docs |
| Order Placement | 10 req/s | Official docs |
| Portfolio | 10 req/s | Official docs |
| Historical | 10 req/s | Official docs |

---

## Authentication

| Flow | Status | Notes |
|------|--------|-------|
| Static Token | ✅ | Works with access_token |
| OAuth PKCE | ✅ | Full flow implemented |
| Token Refresh | ✅ | Via refresh_token |
| Analytics Token | ✅ | 1-year read-only |
| Webhook Token | ✅ | Daily refresh via notifier |

---

## Critical Issues Found

1. **V2 Historical Candle Deprecated** - Must migrate to V3
2. **V2 Intervals Limited** - Only 1minute, 30minute, day, week, month
3. **V3 Intervals Full** - 1-300 minutes, 1-5 hours, 1 day, 1 week, 1 month
4. **Order Book Deprecated** - No replacement endpoint
5. **Option Expiry Deprecated** - No replacement endpoint
