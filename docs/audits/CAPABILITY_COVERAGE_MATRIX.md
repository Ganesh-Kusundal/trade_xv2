# Capability Coverage Matrix

Auto-generated from `domain/capability_manifest.py`.
Do not edit manually — run `python scripts/capability_report.py --markdown`.

## Summary

- Total surfaces: **71**
- exposed: **34**
- partial: **6**
- mismatch: **8**
- gap: **0**
- broker_only: **23**

### P2 gaps (9)

- `market_data.ltp` — No dedicated CLI/REST; used internally by dashboard/validate
- `instruments.search` — 
- `capability.news` — 
- `capability.order_stream` — CLI reports connection status only
- `capability.multi_order` — 
- `capability.oi_pcr_maxpain` — 
- `capability.option_greeks` — 
- `api.portfolio_summary` — 
- `api.symbols` — 

### P3 gaps (5)

- `portfolio.trades_alias` — Alias for get_trade_book on gateway ABC
- `api.backtest` — 
- `api.replay` — 
- `api.analytics` — 
- `api.strategy` — 

## Full Matrix

| ID | Capability | Gateway | Dhan | Upstox | CLI | REST | Status |
|----|------------|---------|------|--------|-----|------|--------|
| `market_data.history` | historical_data | history | historical.get_historical | historical.fetch_candles | historical, history | GET /api/v1/market/candles, GET /api/v1/live/candles | exposed |
| `market_data.quote` | market_data | quote | market_data.get_quote | market_data.get_quote | quote | GET /api/v1/market/quote/{symbol}, GET /api/v1/live/quote/{symbol} | exposed |
| `market_data.ltp` | market_data | ltp | market_data.get_ltp | market_data.get_ltp | — | GET /api/v1/live/ltp/{symbol} | partial [P2] |
| `market_data.depth` | depth | depth | market_data.get_depth | market_data.get_depth | depth | GET /api/v1/live/depth/{symbol} | exposed |
| `derivatives.option_chain` | options_chain | option_chain | options.get_option_chain | options.get_option_chain | option-chain | GET /api/v1/options/chain/{underlying}, GET /api/v1/live/options/chain/{underlying} | exposed |
| `derivatives.future_chain` | futures | future_chain | futures.get_contracts | futures.get_contracts | futures | GET /api/v1/live/futures/chain/{underlying} | exposed |
| `streaming.websocket` | websocket | stream | market_feed.subscribe | market_data_websocket.subscribe | stream, websocket | WS /ws/market, WS /ws/market/{symbol} | exposed |
| `batch.ltp_batch` | market_data | ltp_batch | market_data.get_batch_ltp | market_data.get_ltp | — | — | broker_only |
| `batch.quote_batch` | market_data | quote_batch | market_data.get_batch_quote | market_data.get_quote | — | — | broker_only |
| `batch.history_batch` | historical_data | history_batch | historical.get_historical | historical.fetch_history_batch | — | — | broker_only |
| `orders.place` | order_command | place_order | orders.place_order | order_command.place_order | place-order, place-orders, bracket-order, oco-order, basket-order | POST /api/v1/orders | exposed |
| `orders.cancel` | order_command | cancel_order | orders.cancel_order | order_command.cancel_order | cancel-order | DELETE /api/v1/orders/{order_id} | exposed |
| `orders.modify` | order_command | modify_order | orders.modify_order | order_command.modify_order | modify-order | PUT /api/v1/orders/{order_id} | exposed |
| `orders.query_orderbook` | order_query | get_orderbook | orders.get_orderbook | order_query.get_order_list | orders, oms | GET /api/v1/orders, GET /api/v1/orders/{order_id}, GET /api/v1/live/orders | exposed |
| `orders.query_trades` | historical_trades | get_trade_book | orders.get_trade_book | order_query.get_trades | trades | GET /api/v1/orders/trades, GET /api/v1/orders/tradebook, GET /api/v1/live/trades | exposed |
| `portfolio.positions` | portfolio | positions | portfolio.get_positions | portfolio.get_positions | positions | GET /api/v1/portfolio/positions, GET /api/v1/live/positions | exposed |
| `portfolio.holdings` | portfolio | holdings | portfolio.get_holdings | portfolio.get_holdings | holdings | GET /api/v1/portfolio/holdings, GET /api/v1/live/holdings | exposed |
| `portfolio.funds` | portfolio | funds | portfolio.get_balance | portfolio.get_balance | account, funds | GET /api/v1/live/funds | exposed |
| `portfolio.trades_alias` | historical_trades | trades | orders.get_trade_book | order_query.get_trades | trades | — | partial [P3] |
| `instruments.search` | instrument_search | search | resolver | instrument_resolver.search | search, instruments lookup | GET /api/v1/symbols/search | mismatch [P2] |
| `instruments.load` | instruments | load_instruments | load_instruments | instrument_loader.load | instruments stats | — | broker_only |
| `lifecycle.capabilities` | — | capabilities | — | — | doctor | — | broker_only |
| `lifecycle.describe` | — | describe | — | — | broker | — | broker_only |
| `lifecycle.close` | — | close | close | disconnect | — | — | broker_only |
| `extended.user_profile` | — | extended.get_user_profile | user_profile.get_profile | portfolio.get_profile | profile | GET /api/v1/live/profile | exposed |
| `extended.super_orders` | — | extended.place_super_order | super_orders.place_super_order | — | super-order | POST /api/v1/live/orders/super | exposed |
| `extended.forever_orders` | — | extended.place_forever_order | forever_orders.place_forever_order | gtt.place_forever_order | forever-order | POST /api/v1/live/orders/forever | exposed |
| `extended.conditional_triggers` | alerts | extended.place_conditional_trigger | conditional_triggers.place_trigger | gtt.place_alert | trigger | POST /api/v1/live/alerts/trigger | exposed |
| `extended.margin` | margin | — | margin.calculate | margin.calculate_margin | margin | POST /api/v1/live/margin/calculate | exposed |
| `extended.exit_all` | exit_all | extended.exit_all | exit_all.exit_all | exit_all.exit_all | exit-all | POST /api/v1/live/orders/exit-all, POST /api/v1/portfolio/square-off | exposed |
| `extended.ledger` | — | extended.get_ledger | ledger.get_ledger | portfolio.get_ledger | ledger | GET /api/v1/live/ledger | exposed |
| `extended.edis` | — | extended.authorize_edis | edis.authorize_edis | — | edis | POST /api/v1/live/edis/authorize | exposed |
| `extended.ip_management` | static_ip | extended.set_ip | ip_management.set_ip | static_ip.set_static_ip | ip | GET /api/v1/live/ip, POST /api/v1/live/ip | exposed |
| `extended.gtt_order` | gtt_order | — | — | gtt.place_gtt_order | gtt-order | POST /api/v1/live/orders/gtt | exposed |
| `extended.cover_order` | cover_order | — | — | cover.place_cover_order | cover-order | POST /api/v1/live/orders/cover | exposed |
| `extended.slice_order` | slice_order | — | orders.place_slice_order | slice.place_slice_order | slice-order | POST /api/v1/live/orders/slice | exposed |
| `extended.kill_switch_broker` | kill_switch | — | orders.kill_switch | kill_switch.set_status | risk kill-switch | POST /api/v1/risk/kill-switch | exposed |
| `extended.ipo` | ipo | extended.get_ipos | — | ipo.get_ipos | ipo | GET /api/v1/live/ipo | exposed |
| `extended.mutual_funds` | mutual_funds | extended.place_mutual_fund_order | — | mutual_funds.place_order | mf | GET /api/v1/live/mutual-funds, POST /api/v1/live/mutual-funds | exposed |
| `extended.payments` | payments | extended.initiate_payout | — | payments.initiate_payout | payout | POST /api/v1/live/payments/payout | exposed |
| `extended.fundamentals` | fundamentals | extended.get_pnl | — | fundamentals.get_pnl | fundamentals | GET /api/v1/live/fundamentals/{isin} | broker_only |
| `capability.news` | news | — | — | news.get_news | news | — | partial [P2] |
| `capability.market_status` | market_status | — | — | market_status.get_market_status | — | — | broker_only |
| `capability.order_stream` | order_stream | — | order_stream.connect | — | websocket | — | partial [P2] |
| `capability.idempotency` | idempotency | — | orders | idempotency_cache | — | — | broker_only |
| `capability.multi_order` | multi_order | — | — | order_client.place_multi_order | place-orders | — | partial [P2] |
| `capability.session_risk` | session_risk | — | — | risk_manager | risk status, oms | GET /api/v1/risk/state | exposed |
| `capability.smartlist` | smartlist | — | — | intelligence.get_smartlist | — | — | broker_only |
| `capability.fii_dii` | fii_dii | — | — | intelligence.get_fii_flow | — | — | broker_only |
| `capability.oi_pcr_maxpain` | oi_pcr_maxpain | — | — | intelligence.get_pcr | — | GET /api/v1/options/pcr/{underlying}, GET /api/v1/options/max-pain/{underlying}, GET /api/v1/options/volume-profile/{underlying} | partial [P2] |
| `capability.market_intelligence` | market_intelligence | — | — | intelligence.get_snapshot | — | — | broker_only |
| `capability.tsl` | trailing_stop_loss | — | — | — | — | — | broker_only |
| `capability.mtf` | mtf | — | — | — | — | — | broker_only |
| `capability.webhooks` | webhooks | — | — | feed_authorizer | — | — | broker_only |
| `capability.amo_order` | amo_order | place_order | orders.place_order | order_command.place_order | — | — | broker_only |
| `capability.portfolio_stream` | portfolio_stream | — | — | portfolio_stream | — | — | broker_only |
| `capability.order_slicing` | order_slicing | — | orders.place_slice_order | slice.place_slice_order | — | — | broker_only |
| `capability.depth_30` | depth_30 | depth | market_data.get_depth | market_data.get_depth | depth | — | broker_only |
| `capability.level2_market_data` | level2_market_data | depth_20 | depth_20_feed.subscribe | — | — | — | broker_only |
| `capability.option_greeks` | option_greeks | — | — | market_data_v3.get_option_greeks_v3 | option-chain | GET /api/v1/options/iv-surface/{underlying} | mismatch [P2] |
| `capability.global_markets` | global_markets | — | — | — | — | — | broker_only |
| `capability.volatility_index` | volatility_index | — | — | — | — | — | broker_only |
| `monitoring.api_health` | — | — | — | — | doctor | GET /api/v1/health, GET /api/v1/health/readyz, GET /api/v1/health/metrics, GET /api/v1/health/metrics/prometheus | exposed |
| `monitoring.live_broker_health` | — | — | — | — | doctor | GET /api/v1/live/health, GET /api/v1/live/readyz, GET /api/v1/live/capabilities | exposed |
| `api.scanner` | — | — | — | — | analytics scan | GET /api/v1/scanner/results, GET /api/v1/scanner/top-candidates, GET /api/v1/scanner/snapshots, POST /api/v1/scanner/run | exposed |
| `api.backtest` | — | — | — | — | analytics backtest | POST /api/v1/backtest/run, GET /api/v1/backtest/results/{backtest_id}, GET /api/v1/backtest/comparison/{run_id} | mismatch [P3] |
| `api.replay` | — | — | — | — | analytics replay | GET /api/v1/replay/sessions, POST /api/v1/replay/sessions, GET /api/v1/replay/sessions/{session_id}, POST /api/v1/replay/sessions/{session_id}/play, POST /api/v1/replay/sessions/{session_id}/pause, POST /api/v1/replay/sessions/{session_id}/stop, POST /api/v1/replay/sessions/{session_id}/speed, POST /api/v1/replay/sessions/{session_id}/seek | mismatch [P3] |
| `api.analytics` | — | — | — | — | analytics breadth | GET /api/v1/analytics/market-breadth, GET /api/v1/analytics/indicators, GET /api/v1/analytics/snapshot, GET /api/v1/analytics/top-candidates, GET /api/v1/analytics/relative-strength | mismatch [P3] |
| `api.portfolio_summary` | portfolio | — | — | — | oms | GET /api/v1/portfolio/summary, GET /api/v1/portfolio/pnl | mismatch [P2] |
| `api.symbols` | instruments | — | — | — | instrument | GET /api/v1/symbols/{symbol}, GET /api/v1/symbols/universe/{name} | mismatch [P2] |
| `api.strategy` | — | — | — | — | analytics strategies | GET /api/v1/strategy/signals, GET /api/v1/strategy/candidates, GET /api/v1/analytics/strategies, POST /api/v1/analytics/strategies/run | mismatch [P3] |
