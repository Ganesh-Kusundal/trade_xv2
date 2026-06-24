# Upstox Wire-Format v2 / v3 Audit (REF-22)

This document is the canonical reference for which Upstox API endpoints
the codebase uses, which version (v2 vs v3) each one hits, and where the
host/route lives in the source tree.

If you add a new endpoint, you MUST update both the URL resolver and
this document. If you find an endpoint listed here that has been removed
or renamed, file an issue — the audit relies on this list being accurate.

## Hosts

| Host                              | Protocol | Plan     | Used for                                       |
| --------------------------------- | -------- | -------- | ---------------------------------------------- |
| `api.upstox.com`                  | HTTPS    | Standard | v2 REST: quotes, profile, positions, holdings  |
| `api-hft.upstox.com`              | HTTPS    | HFT      | v3 REST: order place/modify/cancel, GTT        |
| `sandbox-api.upstox.com`          | HTTPS    | Standard | Sandbox for v2                                 |
| `sandbox-api-hft.upstox.com`      | HTTPS    | HFT      | Sandbox for v3                                 |

The codebase uses ONE resolver — `brokers/upstox/auth/urls.py` —
which delegates to `config.endpoints._UpstoxUrls`. All URL strings are
constructed there; no `f"https://api.upstox.com/..."` should appear
elsewhere in the codebase.

## Endpoint inventory (as of this audit)

### Authentication (v2 + v3)

| Method | Endpoint                             | Version | Host              | Resolver method                  |
| ------ | ------------------------------------ | ------- | ----------------- | -------------------------------- |
| GET    | `/v2/login/authorization/dialog`     | v2      | api               | `auth_dialog_url`                |
| POST   | `/v2/login/authorization/token`      | v2      | api               | `auth_token_url`                 |
| POST   | `/v3/login/authorization/token`      | v3      | api-hft           | `token_request_v3_url`           |
| DELETE | `/v2/logout`                         | v2      | api               | `logout_url`                     |
| GET    | `/v2/user/profile`                   | v2      | api               | `profile_url`                    |

### Market data (v2 REST)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/market-quote/ltp`                            | `market_quote_ltp_url`                |
| GET    | `/v2/market-quote/quotes?quote=BEST_FIVE`          | `market_quote_full_url` (depth: 5 levels) |
| GET    | `/v2/market-quote/depth`                          | `market_quote_order_book_url` (unused — returns 404 on some plans) |
| GET    | `/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}` | `historical_candle_url`   |
| GET    | `/v2/market/status/{exchange}`                    | `market_status_url`                   |
| GET    | `/v2/market/holidays`                             | `market_holidays_url`                 |

### Market data (v3 REST, Plus plan)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v3/market-quote/quotes`                         | `market_quote_full_v3_url`            |
| GET    | `/v3/market-quote/option-greeks`                  | `market_quote_option_greeks_v3_url`   |
| GET    | `/v3/market-quote/ltp`                            | `market_quote_ltp_v3_url`             |

### WebSocket authorize

| Method | Endpoint                                          | Version | Resolver method                       |
| ------ | ------------------------------------------------- | ------- | ------------------------------------- |
| POST   | `/v2/feed/authorize`                              | v2      | `feed_authorize_v2_url`               |
| POST   | `/v3/feed/authorize`                              | v3      | `feed_authorize_v3_url`               |
| POST   | `/v2/portfolio/stream/authorize`                  | v2      | `portfolio_stream_authorize_url`      |

### Orders (v3, HFT — primary)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| POST   | `/v3/order/place`                                 | `place_order_v3_url`                  |
| PUT    | `/v3/order/modify`                                | `modify_order_v3_url`                 |
| DELETE | `/v3/order/cancel`                                | `cancel_order_v3_url`                 |

### Orders (v2 — kept for backward-compat tests)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| POST   | `/v2/order/place`                                 | `place_order_v2_url`                  |
| PUT    | `/v2/order/modify`                                | `modify_order_v2_url`                 |
| DELETE | `/v2/order/cancel`                                | `cancel_order_v2_url`                 |
| POST   | `/v2/order/multi/place`                           | `multi_order_v2_url`                  |
| GET    | `/v2/order/retrieve-all`                          | `order_book_url`                      |
| GET    | `/v2/order/history`                               | `order_history_url`                   |
| GET    | `/v2/order/trades/get-trades-for-day`             | `trades_for_day_url`                  |

### GTT (v3, HFT)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| POST   | `/v3/gtt/place`                                   | `gtt_place_url`                       |
| PUT    | `/v3/gtt/modify`                                  | `gtt_modify_url`                      |
| DELETE | `/v3/gtt/cancel`                                  | `gtt_cancel_url`                      |
| GET    | `/v3/gtt/orders`                                  | `gtt_orders_url`                      |
| GET    | `/v3/gtt/order/{id}`                              | `gtt_order_details_url`               |

### Portfolio (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/portfolio/short-term-positions`              | `positions_url`                       |
| GET    | `/v2/portfolio/long-term-holdings`                | `holdings_url`                        |
| GET    | `/v2/user/get-funds-and-margin`                   | `funds_url`                           |
| PUT    | `/v2/portfolio/convert-position`                  | `convert_position_url`                |
| GET    | `/v3/portfolio/mtf-positions`                     | `mtf_positions_v3_url`                |
| GET    | `/v3/user/fund-margin`                            | `user_fund_margin_v3_url`             |

### Options (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/option/contract`                             | `option_contracts_url`                |
| GET    | `/v2/option/chain`                                | `option_chain_url`                    |
| GET    | `/v2/option/expiry`                               | `option_expiry_url`                   |
| GET    | `/v2/option/greeks`                               | `option_greeks_url`                   |

### Margin / Charges (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| POST   | `/v2/margin/requirement`                          | `margin_requirement_url`              |
| GET    | `/v2/charges/brokerage`                           | `charges_brokerage_url`               |
| GET    | `/v2/charges/margin`                              | `charges_margin_url`                  |

### Expired instruments (Plus plan, v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/expired-instruments/expiries`                | `expired_expiries_url`                |
| GET    | `/v2/expired-instruments/option/contract`         | `expired_option_contract_url`         |
| GET    | `/v2/expired-instruments/historical-candle/{key}/{interval}/{to_date}/{from_date}` | `expired_historical_candle_url` |
| GET    | `/v2/expired-instruments/future/contract`         | `expired_future_contracts_url`        |

### News / market intelligence (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/news`                                        | `news_url`                            |
| GET    | `/v2/market-intelligence/pcr`                     | `pcr_url`                             |
| GET    | `/v2/market-intelligence/max-pain`                | `max_pain_url`                        |
| GET    | `/v2/market-intelligence/oi`                      | `oi_url`                              |
| GET    | `/v2/market-intelligence/fii`                     | `fii_url`                             |
| GET    | `/v2/market-intelligence/dii`                     | `dii_url`                             |
| GET    | `/v2/market-intelligence/smartlist-futures`       | `smartlist_futures_url`               |
| GET    | `/v2/market-intelligence/smartlist-options`       | `smartlist_options_url`               |

### Instruments (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/instruments/{segment}`                       | `instrument_master_url`               |
| GET    | `/v2/search/instruments`                          | `instrument_search_url`               |
| GET    | `/v2/instruments/complete`                        | `instrument_complete_url`             |

### User / risk (v2/v3)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| POST   | `/v2/user/kill-switch`                            | `kill_switch_url`                     |
| POST   | `/v2/user/static-ip`                              | `static_ip_url`                       |

### Payments / IPO / MF (v2)

| Method | Endpoint                                          | Resolver method                       |
| ------ | ------------------------------------------------- | ------------------------------------- |
| GET    | `/v2/payments`                                    | `payouts_url`                         |
| GET    | `/v2/ipo`                                         | `ipo_url`                             |
| GET    | `/v2/mutual-funds/holdings`                       | `mutual_funds_holdings_url`           |
| POST   | `/v2/mutual-funds/order`                          | `mutual_funds_order_url`              |
| GET    | `/v2/fundamentals/financials/{isin}/{statement}`  | `fundamentals_financials_url`         |

## Migration rules

1. **No inline URL strings.** Every Upstox URL is built by
   `UpstoxApiUrlResolver` (or, internally, by `_UpstoxUrls`). A
   grep for `https://api.upstox.com` or `https://api-hft.upstox.com`
   in production code MUST return zero results outside the resolver
   and the test fixtures.

2. **Prefer v3 for write paths.** Order place/modify/cancel MUST
   use the v3 (HFT) endpoints. The v2 methods exist only because
   some legacy clients still consume them; new code MUST NOT call
   `place_order_v2_url`, `modify_order_v2_url`, or
   `cancel_order_v2_url` — they are present in the resolver for
   test fixtures and emergency fallback only.

3. **Auth token refresh is v3.** The OAuth code-exchanged-for-token
   flow uses `token_request_v3_url`. The v2 token endpoint
   (`auth_token_url`) is kept for the legacy authorization-code
   dance but new integrations MUST use v3.

4. **WebSocket feeds support both v2 and v3.** The choice depends
   on the data plan. `feed_authorize_v2_url` returns an HFT WS URL
   on `api-hft.upstox.com`; `feed_authorize_v3_url` returns the
   same host but with v3 protobuf schema.

## Test guard

`brokers/upstox/tests/unit/test_url_resolver.py` asserts that every
endpoint above is reachable from the resolver and that the host
matches the expected prefix. If the audit ever drifts from the
resolver, that test will fail — making this document a contractual
artefact, not just a description.
