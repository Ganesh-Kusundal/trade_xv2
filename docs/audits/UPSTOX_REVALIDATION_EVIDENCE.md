# Upstox Revalidation Evidence

- Generated: 2026-06-24T10:24:10.142275
- Python: 3.13.5
- Token: token valid
- Market open: True

## Depth

| Probe | Pass | Detail |
|-------|------|--------|
| D-RELIANCE | False | Upstox API GET https://api.upstox.com/v2/market-quote/quotes failed: HTTP 401 |
| D-NIFTY | False | Upstox API GET https://api.upstox.com/v2/market-quote/quotes failed: HTTP 401 |

## Option Chain

| Probe | Pass | Detail |
|-------|------|--------|
| O1-expiries | False | count=0 sample=[] |
| O2-chain | False | expiry= strikes=0 |

## Future Chain

| Probe | Pass | Detail |
|-------|------|--------|
| F-futures | False | Upstox API GET https://api.upstox.com/v2/expired-instruments/future/contract failed: HTTP 401 |

## Historical

| Probe | Pass | Detail |
|-------|------|--------|
| H-history | False | unsupported type for timedelta days component: datetime.date |

## WebSocket

| Probe | Pass | Detail |
|-------|------|--------|
| W1-ws | False | Upstox API GET https://api-hft.upstox.com/v3/feed/market-data-feed/authorize failed: HTTP 404 |
