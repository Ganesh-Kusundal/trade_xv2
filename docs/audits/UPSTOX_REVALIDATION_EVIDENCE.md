# Upstox Revalidation Evidence

- Generated: 2026-06-30T16:56:02.670291
- Python: 3.13.5
- Token: token valid
- Market open: False

## Depth

| Probe | Pass | Detail |
|-------|------|--------|
| D-RELIANCE | True | bids=5 asks=5 endpoint=GET /v2/market-quote/quotes?quote=BEST_FIVE |
| D-NIFTY | False | bids=0 asks=0 endpoint=GET /v2/market-quote/quotes?quote=BEST_FIVE |

## Option Chain

| Probe | Pass | Detail |
|-------|------|--------|
| O1-expiries | False | count=0 sample=[] |
| O2-chain | False | expiry= strikes=0 |

## Future Chain

| Probe | Pass | Detail |
|-------|------|--------|
| F-futures | False | Upstox API GET https://api.upstox.com/v2/expired-instruments/future/contract failed: HTTP 400 |

## Historical

| Probe | Pass | Detail |
|-------|------|--------|
| H1-gateway-history | True | rows=20 first_tz=Asia/Kolkata |

## WebSocket

| Probe | Pass | Detail |
|-------|------|--------|
| W1-ws | True | skipped — market closed |
