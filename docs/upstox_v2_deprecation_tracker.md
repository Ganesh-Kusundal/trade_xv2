# Upstox V2 Deprecation Tracker

Tracks V2 endpoints still in use, their V3 equivalents, and migration status.

> Last updated: 2026-06-25

## Summary

| Category | V2 Endpoints Active | V3 Migrated | Pending |
|----------|---------------------|-------------|---------|
| Market Data | 5 | 5 | 0 |
| Orders | 4 | 3 | 1 |
| Portfolio | 4 | 1 | 3 |
| Options | 4 | 0 | 4 |
| Historical | 1 | 1 | 0 |
| Auth | 3 | 1 | 2 |
| Market Intelligence | 5 | 0 | 5 |
| Instruments | 3 | 0 | 3 |
| GTT | 4 | 3 | 1 |

---

## Market Data

### LTP (Last Traded Price)

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market-quote/ltp` | `client_v2.py:get_ltp()` | **Active** — used by `market_data_adapter.py:quote()`, `ltp()` |
| V3 | `GET /v3/market-quote/ltp` | `client_v3.py:get_ltp_v3()` | **Migrated** — V3 client exists, not yet wired into adapter |

### Full Quote

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market-quote/quotes` | `client_v2.py:get_quote()` | **Active** — primary quote source in adapter |
| V3 | `GET /v3/market-quote/quotes` | `client_v3.py:get_full_quote()` | **Migrated** — V3 client exists, not yet wired into adapter |

### OHLC

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market-quote/ohlc` | `client_v2.py:get_ohlc()` | **Active** — used for OHLC data |
| V3 | — | — | **No V3 equivalent yet** |

### Order Book

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market-quote/order-book` | `client_v2.py:get_order_book()` | **Active** — used by adapter `depth()` |
| V3 | — | — | **No V3 equivalent yet** |

### Option Greeks

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market-quote/option-greeks` | `options_client.py` | **Active** |
| V3 | `GET /v3/market-quote/option-greeks` | `client_v3.py:get_option_greeks_v3()` | **Migrated** |

---

## Orders

### Place / Modify / Cancel

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `POST /v2/order/place` | — | **Deprecated** — use V3 |
| V3 | `POST /v3/order/place` | `order_client.py` | **Active** — primary order path |
| V3 | `PUT /v3/order/modify` | `order_client.py` | **Active** |
| V3 | `DELETE /v3/order/cancel` | `order_client.py` | **Active** |

### Order Book / History

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/order/book` | `order_query_adapter.py` | **Active** |
| V2 | `GET /v2/order/history` | `order_query_adapter.py` | **Active** |
| V2 | `GET /v2/order/trades-for-day` | `order_query_adapter.py` | **Active** |
| V2 | `GET /v2/order/trades` | `order_query_adapter.py` | **Active** |

> Note: Order queries remain on V2. Upstox has not yet published V3 equivalents for order book/history.

---

## Portfolio

### Positions

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/portfolio/short-term-positions` | `portfolio_adapter.py` | **Active** |
| V3 | `GET /v3/portfolio/short-term-positions` | `portfolio_client.py` | **Migrated** |

### Holdings

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/portfolio/long-term-holdings` | `portfolio_adapter.py` | **Active** |
| V3 | — | — | **No V3 equivalent yet** |

### Funds

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/user/get-funds-and-margin` | `portfolio_adapter.py` | **Active** |
| V3 | `GET /v3/user/fund-margin` | `client_v3.py:get_funds_v3()` | **Migrated** |

### MTF Positions

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | — | — | **No V2 equivalent** |
| V3 | `GET /v3/portfolio/positions/mtf` | `client_v3.py:get_mtf_positions()` | **V3-only** |

### Convert Position

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `PUT /v2/portfolio/short-term-positions/convert` | `portfolio_adapter.py` | **Active** |
| V3 | — | — | **No V3 equivalent yet** |

---

## Historical Candles

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/historical-candle/{key}/{interval}/{to}/{from}` | `historical_v2.py` | **Active** — used by `market_data_adapter.py:history()` |
| V3 | `GET /v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}` | `historical_v3.py` | **Migrated** — V3 client exists, supports custom intervals |

> V3 historical uses different path structure: `/v3/historical-candle/{key}/{unit}/{interval}/{to_date}[/{from_date}]` with `unit` as `minutes|hours|days|weeks|months`.

---

## Options Chain

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/option/chain` | `options_client.py` | **Active** |
| V2 | `GET /v2/option/expiries` | `options_client.py` | **Active** |
| V2 | `GET /v2/option/contracts` | `options_client.py` | **Active** |
| V2 | `GET /v2/option/greeks` | `options_client.py` | **Active** |
| V3 | `GET /v3/market-quote/option-greeks` | `client_v3.py` | **Partial** — only greeks, no chain/expiry |

---

## Auth / Profile

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/login/authorization/dialog` | `oauth_client.py` | **Active** — OAuth dialog |
| V2 | `POST /v2/login/authorization/token` | `oauth_client.py` | **Active** — token exchange |
| V2 | `GET /v2/user/profile` | — | **Active** |
| V3 | `POST /v3/login/auth/token/request/{client_id}` | — | **Migrated** — new token request flow |

---

## Market Intelligence (V2-only)

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/market/oi` | `market_intelligence/client.py` | **Active** |
| V2 | `GET /v2/market/max-pain` | `market_intelligence/client.py` | **Active** |
| V2 | `GET /v2/market/pcr` | `market_intelligence/client.py` | **Active** |
| V2 | `GET /v2/market/fii` | `market_intelligence/client.py` | **Active** |
| V2 | `GET /v2/market/dii` | `market_intelligence/client.py` | **Active** |

> No V3 equivalents published yet.

---

## Instruments (V2-only)

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | `GET /v2/instrument/master` | `instruments/loader.py` | **Active** |
| V2 | `GET /v2/instrument/search` | `instruments/search.py` | **Active** |
| V2 | `GET /v2/instrument/complete` | `instruments/loader.py` | **Active** |

> No V3 equivalents published yet.

---

## GTT (Good Till Triggered)

| Version | Endpoint | Client | Status |
|---------|----------|--------|--------|
| V2 | — | — | **No V2 equivalent** |
| V3 | `POST /v3/order/gtt/place` | `gtt_client.py` | **V3-only** |
| V3 | `PUT /v3/order/gtt/modify` | `gtt_client.py` | **V3-only** |
| V3 | `DELETE /v3/order/gtt/cancel` | `gtt_client.py` | **V3-only** |
| V2 | `GET /v2/order/gtt` | `gtt_client.py` | **Active** — query remains V2 |

---

## Migration Priority

### High Priority (V3 available, adapter not yet migrated)

1. **LTP** — `client_v3.py:get_ltp_v3()` ready, wire into `market_data_adapter.py`
2. **Full Quote** — `client_v3.py:get_full_quote()` ready, wire into adapter
3. **Historical Candles** — `historical_v3.py` ready, supports richer intervals
4. **Funds** — `client_v3.py:get_funds_v3()` ready

### Medium Priority (V3 partial)

5. **Option Greeks** — V3 greeks available, chain/expiry still V2
6. **Portfolio Positions** — V3 exists, holdings still V2

### Low Priority (No V3 yet)

7. **Order Book** — no V3 equivalent
8. **OHLC** — no V3 equivalent
9. **Order Queries** — book/history/trades remain V2
10. **Market Intelligence** — all endpoints V2-only
11. **Instruments** — all endpoints V2-only
12. **Options Chain** — chain/expiry/contracts V2-only
13. **Auth Dialog** — V2 OAuth flow still required
