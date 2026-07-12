# D0.7 — API Surface Inventory

> Generated from live source file reads of `/Users/apple/Downloads/Trade_XV2`

---

## 1. SDK API — `BrokerSession`

**Source:** `src/brokers/session/broker_session.py`

The primary Python entry point. Thin, broker-agnostic facade over the composition-root `Session`.

| Method | Signature | Backed By |
|---|---|---|
| `BrokerSession(broker, *, mode, event_bus, env_path, load_instruments, run_selftest, **kwargs)` | constructor | `tradex.session.open_session` → `RuntimeBundle` |
| `.connect(broker, **kwargs)` | classmethod → `BrokerSession` | delegates to `__init__` |
| `.runtime` | property → `RuntimeBundle` | session-scoped runtime coordinators |
| `.broker_id` | property → `str` | — |
| `.session` | property → `DomainSession` | composition-root session (escape hatch) |
| `.universe` | property → `Universe` | `Session.universe` |
| `.provider` | property → `DataProvider` | `Session.provider` |
| `.status` | property → `Any` | `Session.status` |
| `.stock(symbol, exchange)` | → `Equity` | `Session.universe.equity` |
| `.equity(symbol, exchange)` | → `Equity` | alias for `.stock()` |
| `.etf(symbol, exchange)` | → `ETF` | `Session.universe.etf` |
| `.index(name, exchange)` | → `Index` | `Session.universe.index` |
| `.spot(symbol, exchange)` | → `Spot` | `Session.universe.spot` |
| `.currency(symbol, exchange)` | → `Currency` | `Session.universe.currency` |
| `.future(symbol, *, expiry, exchange)` | → `Future` | `Session.universe.future` |
| `.commodity(symbol, *, expiry, exchange)` | → `Commodity` | `Session.universe.commodity` |
| `.option(underlying, strike, right, *, expiry, exchange, leg)` | → `Option` | `Session.universe.option` |
| `.option_chain(underlying, *, expiry, exchange)` | → `OptionChain` | `Session.option_chain` |
| `.quote(instrument)` | → `Quote` | `RuntimeBundle.quotes.quote` |
| `.history(instrument, timeframe, days)` | → `HistoricalSeries` | `RuntimeBundle.history.series` |
| `.subscribe(instrument, callback, *, depth)` | → `SubscriptionHandle` | `RuntimeBundle.subscriptions.subscribe` |
| `.unsubscribe(instrument)` | → `None` | `RuntimeBundle.subscriptions.unsubscribe` |
| `.buy(instrument, quantity, price, order_type, product_type)` | → `Order` | `RuntimeBundle.execution.buy` |
| `.sell(instrument, quantity, price, order_type, product_type)` | → `Order` | `RuntimeBundle.execution.sell` |
| `.account` | property → `AccountView` | `Session.account` |
| `.orders()` | → `list` | `RuntimeBundle.execution.orders` |
| `.cancel(order_id)` | → `Any` | `Session.cancel` |
| `.modify(order_id, **changes)` | → `Any` | `Session.modify` |
| `.instrument_id(symbol, exchange)` | → `str` | resolves via `.stock().id` |
| `.broker_capabilities(symbol)` | → `dict` | `brokers.services.core.format_session_capabilities` |
| `.close()` | → `None` | `Session.close` |

**Total SDK public surface:** 27 methods + 6 properties + 1 constructor + 1 classmethod

---

## 2. CLI API — Click Commands

**Source:** `src/brokers/cli/broker.py`

Entry point registered in `pyproject.toml` as `broker` console script.

| Command | Description | Backed By |
|---|---|---|
| `broker` (root group) | CLI group — `-b/--broker` selects broker | — |
| `shell` | Interactive shell with auto-reconnect | `BrokerSession` + `_shell_invoke` |
| `connect` | Connect to broker, show startup checkpoints | `brokers.services.run_connect` |
| `discover` | Discover available brokers/plugins | `SessionFactory.discover` |
| `quote` | Fetch live quote | `get_quote` service |
| `history` | Fetch historical OHLCV bars | `get_history` service |
| `subscribe` | Probe live subscription | `run_subscribe_probe` |
| `depth` | Fetch market depth | `get_depth` service |
| `option-chain` | Fetch option chain | `get_option_chain` service |
| `positions` | Show open positions | `get_positions` service |
| `holdings` | Show portfolio holdings | `get_holdings` service |
| `funds` | Show available funds/margin | `get_funds` service |
| `orders` | List orders | `get_orders` service |
| `order` | Place order (buy/sell) | `place_order` service |
| `cancel` | Cancel an order | `cancel_order` service |
| `modify` | Modify an open order | `modify_order` service |
| `capability` | Show broker capabilities | `get_capabilities` service |
| `symbols` | Resolve symbol to instrument id | `lookup_symbol` service |
| `instrument` | Resolve symbol to instrument metadata | `lookup_instrument` service |
| `security` | Resolve symbol to security info | `lookup_security` service |
| `mappings` | Run symbol mapping validation | `run_mapping` (platform_ops) |
| `diagnose` | Run diagnostics suite | `run_diagnose` (platform_ops) |
| `health` | Run broker health checks | `run_health` (platform_ops) |
| `doctor` | Run full pre-flight validation | `run_doctor` (platform_ops) |
| `benchmark` | Run performance benchmark | `run_benchmark` (platform_ops) |
| `market-hours` | Show market hours status | `market_hours` (platform_ops) |
| `depth20` | Fetch 20-level depth | `get_depth` service |
| `depth200` | Fetch 200-level depth | `get_depth` service |
| `depth30` | Fetch 30-level depth | `get_depth` service |
| `news` | Fetch broker news feed | `get_news` service |
| `super-orders` | List super orders | `get_orders` service |
| `forever-orders` | List forever orders | `get_orders` service |
| `certify` | Run broker certification suite | `run_certify` (platform_ops) |
| `verify` | Run startup self-test | `run_verify` (platform_ops) |

**Total CLI commands:** 34

---

## 3. MCP API — FastMCP Tools

**Source:** `src/brokers/mcp/tools.py`

All tools are registered with the `FastMCP("brokers")` server via `register_tools()`.

| Tool | Description | Service Function |
|---|---|---|
| `broker_connect` | Connect to broker, return session status | `platform_ops.run_connect` |
| `broker_quote` | Fetch live quote for a symbol | `services.get_quote` |
| `broker_history` | Fetch historical OHLCV bars | `services.get_history` |
| `broker_subscribe` | Probe live subscription | `platform_ops.run_subscribe_probe` |
| `broker_positions` | Return open positions | `services.get_positions` |
| `broker_holdings` | Return portfolio holdings | `services.get_holdings` |
| `broker_funds` | Return available funds/margin | `services.get_funds` |
| `broker_orders` | List orders for session | `services.get_orders` |
| `broker_place_order` | Place an order via OMS | `services.place_order` |
| `broker_modify_order` | Modify an open order | `services.modify_order` |
| `broker_cancel_order` | Cancel an open order | `services.cancel_order` |
| `broker_option_chain` | Fetch option chain | `services.get_option_chain` |
| `broker_market_depth` | Fetch market depth | `services.get_depth` |
| `broker_health` | Run broker health checks | `platform_ops.run_health` |
| `broker_capabilities` | List broker capabilities | `services.get_capabilities` |
| `broker_symbol_lookup` | Resolve symbol to instrument id | `services.lookup_symbol` |
| `broker_instrument_lookup` | Resolve symbol to metadata | `services.lookup_instrument` |
| `broker_news` | Fetch broker news feed | `services.get_news` |
| `broker_verify` | Run startup self-test | `platform_ops.run_verify` |
| `broker_doctor` | Run full pre-flight validation | `platform_ops.run_doctor` |
| `broker_diagnose` | Run diagnostics suite | `platform_ops.run_diagnose` |
| `broker_benchmark` | Run performance benchmark | `platform_ops.run_benchmark` |
| `broker_certify` | Run full certification suite | `platform_ops.run_certify` |
| `broker_mappings` | Run symbol mapping validation | `platform_ops.run_mapping` |

**Total MCP tools:** 24

---

## 4. REST API — FastAPI Endpoints

**Source:** `src/interface/api/routers/` + `src/interface/api/main.py`

All routes use prefix `/api/v1` (configurable via `APIConfig.api_prefix`).

### Health (`/api/v1/health`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe | `infrastructure.health.health_registry.run_all()` |
| `GET` | `/api/v1/health/readyz` | Readiness probe | `application.services.api_readiness.evaluate_api_readiness` |
| `GET` | `/api/v1/health/ready` | Readiness alias | same as `/readyz` |
| `GET` | `/api/v1/health/metrics` | Observability metrics JSON | `interface.api.middleware.http_metrics` + `EventMetrics` |
| `GET` | `/api/v1/health/metrics/prometheus` | Prometheus text format | `PrometheusExporter.generate()` |

### Symbols (`/api/v1/symbols`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/symbols/search` | Search symbols | `DataCatalog` (DuckDB) |
| `GET` | `/api/v1/symbols/{symbol}` | Symbol metadata | `DataCatalog` (DuckDB) |
| `GET` | `/api/v1/symbols/universe/{name}` | Universe symbols | `data/universes/` files |

### Market Data (`/api/v1/market`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/market/candles` | Historical OHLCV (datalake) | `DataLakeGateway.query_candles` |
| `GET` | `/api/v1/market/live/candles` | Historical OHLCV (live broker) | `MarketDataComposer.fetch_historical` |
| `GET` | `/api/v1/market/quote/{symbol}` | Latest quote snapshot | `Session.universe.equity().refresh()` |

### Analytics (`/api/v1/analytics`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/analytics/indicators` | Technical indicators | DuckDB `ViewManager` (v_feature_*) |
| `GET` | `/api/v1/analytics/relative-strength` | RS rankings | `analytics.ranking.RankingEngine` |
| `GET` | `/api/v1/analytics/market-breadth` | Market breadth | `analytics.market_breadth.BreadthAnalytics` |
| `GET` | `/api/v1/analytics/strategies` | List registered strategies | `MultiStrategyRuntime.list_strategies` |
| `POST` | `/api/v1/analytics/strategies/run` | Build multi-strategy pipeline | `StrategyRegistry.discover` + `MultiStrategyRuntime.create_pipeline` |

### Scanner (`/api/v1/scanner`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/scanner/results` | Historical scan results | `datalake.research.scan_store.get_recent_scans` |
| `GET` | `/api/v1/scanner/top-candidates` | Top scanner candidates | DuckDB `v_top3/v_top10_candidates` |
| `GET` | `/api/v1/scanner/snapshots` | Full intraday snapshots | DuckDB `v_intraday_snapshot` |
| `POST` | `/api/v1/scanner/run` | Trigger scanner run | `analytics.scanner.runner.ScannerRunner` |

### Strategy (`/api/v1/strategy`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/strategy/signals` | Strategy signals | DuckDB `v_strategy_*` views |
| `GET` | `/api/v1/strategy/candidates` | Strategy candidates | DuckDB `v_strategy_candidates` |

### Options (`/api/v1/options`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/options/chain/{underlying}` | Option chain | DuckDB + Parquet (options/candles) |
| `GET` | `/api/v1/options/pcr/{underlying}` | Put-Call Ratio | DuckDB `v_pcr` |
| `GET` | `/api/v1/options/max-pain/{underlying}` | Max pain | DuckDB `v_max_pain` |
| `GET` | `/api/v1/options/iv-surface/{underlying}` | IV surface | DuckDB `v_iv_surface` |
| `GET` | `/api/v1/options/volume-profile/{underlying}` | Options volume profile | DuckDB + Parquet |

### Replay (`/api/v1/replay`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/replay/sessions` | List sessions | `ReplaySessionStore` |
| `POST` | `/api/v1/replay/sessions` | Create session | `ReplaySessionStore` |
| `GET` | `/api/v1/replay/sessions/{session_id}` | Get session | `ReplaySessionStore` |
| `POST` | `/api/v1/replay/sessions/{session_id}/play` | Play replay | `analytics.replay.ReplayEngine` |
| `POST` | `/api/v1/replay/sessions/{session_id}/pause` | Pause replay | `ReplaySessionStore` |
| `POST` | `/api/v1/replay/sessions/{session_id}/stop` | Stop replay | `ReplaySessionStore` |
| `POST` | `/api/v1/replay/sessions/{session_id}/speed` | Set playback speed | `ReplaySessionStore` |
| `POST` | `/api/v1/replay/sessions/{session_id}/seek` | Seek to timestamp | `ReplaySessionStore` |

### Backtest (`/api/v1/backtest`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `POST` | `/api/v1/backtest/run` | Run backtest | `analytics.backtest.BacktestEngine` |
| `GET` | `/api/v1/backtest/results/{backtest_id}` | Get result | `BacktestCacheStore` |
| `GET` | `/api/v1/backtest/comparison/{run_id}` | Compare runs | `BacktestCacheStore` |

### Portfolio (`/api/v1/portfolio`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/portfolio/positions` | Positions | `application.portfolio.portfolio_service.PortfolioService` |
| `GET` | `/api/v1/portfolio/holdings` | Holdings | `PortfolioService.get_holdings` |
| `GET` | `/api/v1/portfolio/summary` | Portfolio summary | `PositionRepository` + `RiskManager` |
| `GET` | `/api/v1/portfolio/pnl` | P&L history | `TradeJournal` / `PositionRepository` |
| `POST` | `/api/v1/portfolio/square-off` | Square off positions | `application.oms.square_off_service.SquareOffService` |

### Orders (`/api/v1/orders`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/orders` | List orders | OMS order store |
| `GET` | `/api/v1/orders/trades` | List trades | OMS trade store |
| `GET` | `/api/v1/orders/tradebook` | Full tradebook | OMS trade store |
| `GET` | `/api/v1/orders/{order_id}` | Single order | OMS order store |
| `POST` | `/api/v1/orders` | Place order | `ExecutionComposer` |
| `PUT` | `/api/v1/orders/{order_id}` | Modify order | `ExecutionComposer` |
| `DELETE` | `/api/v1/orders/{order_id}` | Cancel order | `ExecutionComposer` |

### Risk (`/api/v1/risk`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/risk/state` | Risk state snapshot | `application.oms.risk_manager.RiskManager.snapshot` |
| `POST` | `/api/v1/risk/kill-switch` | Toggle kill switch (admin) | `RiskManager.set_kill_switch` |

### Audit (`/api/v1/audit`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/audit/events` | Query audit events | `application.audit.audit_logger.store` |
| `GET` | `/api/v1/audit/events/{event_id}` | Single audit event | `audit_logger.store.get` |
| `GET` | `/api/v1/audit/stats` | Audit statistics | `audit_logger.store.count` + `.query` |

### News (`/api/v1/news`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/news` | Fetch market/instrument news | `BrokerService.active_broker.news` |

### Feature Flags (`/api/v1/flags`)

| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/flags` | List all feature flags | `config.feature_flags.FeatureFlags` |
| `GET` | `/api/v1/flags/{name}` | Get flag info | `FeatureFlags.get_flag_info` |
| `POST` | `/api/v1/flags/{name}/toggle` | Toggle flag (admin) | `FeatureFlags.set_flag` |
| `POST` | `/api/v1/flags/{name}/rollout` | Set rollout % (admin) | `FeatureFlags.set_rollout_percentage` |

### Live Broker (`/api/v1/live`)

#### Live Health
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/health` | Gateway health + token presence | `gateway.describe()` |
| `GET` | `/api/v1/live/readyz` | Production readiness | `ProductionReadinessChecker.run` |
| `GET` | `/api/v1/live/capabilities` | Gateway capabilities matrix | `gateway.capabilities()` |

#### Live Market
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/market/quote/{symbol}` | Live quote (domain object) | `Session.universe.equity().refresh()` |
| `GET` | `/api/v1/live/market/ltp/{symbol}` | Live LTP | `Session.universe.equity().refresh()` |
| `GET` | `/api/v1/live/market/depth/{symbol}` | Live depth | `Instrument.depth()` |
| `GET` | `/api/v1/live/market/candles` | Live candles | `Instrument.history()` |

#### Live Portfolio
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/portfolio/positions` | Live positions | `BrokerSession.account.positions` |
| `GET` | `/api/v1/live/portfolio/holdings` | Live holdings | `BrokerSession.account.holdings` |
| `GET` | `/api/v1/live/portfolio/funds` | Live funds | `BrokerSession.account.funds` |

#### Live Orders
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/orders/orders` | Live orderbook | `gateway.get_orderbook()` |
| `GET` | `/api/v1/live/orders/trades` | Live trades | `gateway.get_trade_book()` |

#### Live Derivatives
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/derivatives/options/chain/{underlying}` | Live option chain | `gateway.option_chain()` |
| `GET` | `/api/v1/live/derivatives/futures/chain/{underlying}` | Live future chain | `gateway.future_chain()` |

#### Live Extended (capability-gated)
| Method | Path | Description | Backed By |
|---|---|---|---|
| `GET` | `/api/v1/live/extended/profile` | User profile | `gateway.extended.get_user_profile()` |
| `POST` | `/api/v1/live/extended/orders/super` | Super order | `ExtendedOrderService.place_super_order` |
| `POST` | `/api/v1/live/extended/orders/forever` | Forever order | `ExtendedOrderService.place_forever_order` |
| `POST` | `/api/v1/live/extended/alerts/trigger` | Alert trigger | `ExtendedOrderService.place_trigger` |
| `POST` | `/api/v1/live/extended/margin/calculate` | Margin calculation | `BrokerMargin.calculate` |
| `POST` | `/api/v1/live/extended/orders/exit-all` | Exit all positions | `ExtendedOrderService.exit_all` |
| `GET` | `/api/v1/live/extended/ledger` | Ledger (date range) | `gateway.extended.get_ledger()` |
| `POST` | `/api/v1/live/extended/edis/authorize` | EDIS authorization | `gateway.extended.authorize_edis()` (Dhan) |
| `GET` | `/api/v1/live/extended/ip` | Get static IP | `gateway.extended.get_ip()` / `StaticIP.get_static_ip()` |
| `POST` | `/api/v1/live/extended/ip` | Set static IP | `gateway.extended.set_ip()` / `StaticIP.set_static_ip()` |
| `POST` | `/api/v1/live/extended/orders/gtt` | GTT order | `ExtendedOrderService.place_gtt` |
| `POST` | `/api/v1/live/extended/orders/cover` | Cover order | `ExtendedOrderService.place_cover_order` |
| `POST` | `/api/v1/live/extended/orders/slice` | Slice order | `ExtendedOrderService.place_slice_order` |
| `POST` | `/api/v1/live/extended/kill-switch` | Kill switch (admin) | `ExtendedOrderService.set_kill_switch` |
| `GET` | `/api/v1/live/extended/ipo` | IPO listing (Upstox) | `gateway.extended.get_ipos()` |
| `GET` | `/api/v1/live/extended/mutual-funds` | MF holdings (Upstox) | `gateway.extended.get_mutual_fund_holdings()` |
| `POST` | `/api/v1/live/extended/mutual-funds` | MF order (Upstox) | `gateway.extended.place_mutual_fund_order()` |
| `POST` | `/api/v1/live/extended/payments/payout` | Payout (Upstox) | `gateway.extended.initiate_payout()` |
| `GET` | `/api/v1/live/extended/fundamentals/{isin}` | Fundamentals (Upstox) | `gateway.extended.get_pnl()` |

#### Webhook
| Method | Path | Description | Backed By |
|---|---|---|---|
| `POST` | `/api/v1/live/webhook/upstox/token-callback` | Upstox daily token callback | `TokenManager.upgrade_from_webhook` |

### REST API Summary

| Router | Endpoints |
|---|---:|
| Health | 5 |
| Symbols | 3 |
| Market Data | 3 |
| Analytics | 5 |
| Scanner | 4 |
| Strategy | 2 |
| Options | 5 |
| Replay | 8 |
| Backtest | 3 |
| Portfolio | 5 |
| Orders | 7 |
| Risk | 2 |
| Audit | 3 |
| News | 1 |
| Feature Flags | 4 |
| Live Health | 3 |
| Live Market | 4 |
| Live Portfolio | 3 |
| Live Orders | 2 |
| Live Derivatives | 2 |
| Live Extended | 19 |
| Webhook | 1 |
| **Total** | **97** |

---

## 5. WebSocket Endpoints

**Source:** `src/interface/api/ws/market.py`, `src/interface/api/ws/replay.py`

Mounted at prefix `/ws`.

| Path | Protocol | Description | Client Messages | Server Messages |
|---|---|---|---|---|
| `/ws/market` | WebSocket | Multi-symbol real-time market data | `subscribe`, `unsubscribe`, `ping` | `quote`, `candle`, `subscribed`, `unsubscribed`, `pong`, `error` |
| `/ws/market/{symbol}` | WebSocket | Single-symbol market data (auto-subscribe) | (keepalive only) | `quote`, `candle` |
| `/ws/replay/{session_id}` | WebSocket | Replay market data stream | `play`, `pause`, `stop`, `seek`, `speed`, `ping` | `replay_candle`, `replay_state`, `pong`, `error` |

**Connection management:** `MarketConnectionManager` with per-connection backpressure (`asyncio.Queue`, max 256 messages), sequence numbering for gap detection, and max 500 concurrent connections.

**Wiring:** `MarketBridge` connects `EventBus` → `MarketConnectionManager`, translating domain events to WebSocket payloads.

---

## 6. Agent Tools

**Source:** `src/interface/agent/tools.py`

AI agent surface — one `AgentTools` instance per agent session, each with its own `AgentGuardrails`.

| Tool | Signature | Backed By |
|---|---|---|
| `get_quote(symbol, exchange)` | → `dict` | `Session.universe.equity(symbol).refresh()` |
| `get_history(symbol, exchange, timeframe, days)` | → `HistoricalSeries` | `Instrument.history(timeframe, days)` |
| `get_option_chain(symbol, expiry)` | → `OptionChain` | `Session.option_chain(symbol, expiry)` |
| `get_positions()` | → `list` | `Session.account.refresh().positions` |
| `get_portfolio()` | → `dict` | `Session.account.refresh().portfolio` |
| `get_risk_status()` | → `dict` | `Session.account.risk_profile` |
| `place_order(symbol, exchange, side, quantity, order_type, price, *, dry_run)` | → `Any` or `DryRunResult` | `Instrument.buy()` / `.sell()` or dry-run |
| `cancel_order(order_id)` | → `Any` | `Session.cancel(order_id)` |
| `modify_order(order_id, **changes)` | → `Any` | `Session.modify(order_id, **changes)` |
| `diagnose(broker)` | → `dict` | `brokers.diagnostics.doctor.run_doctor` |
| `diagnose_stream(broker)` | → `dict` | `BrokerDiagnostics.run_all_checks` |
| `check_readiness()` | → `dict` | `application.services.api_readiness.evaluate_api_readiness` |

**Guardrails:** Every tool call passes through `AgentGuardrails.check_rate_limit(action)` and `.check_symbol_allowed(symbol)`. Rate limits: `read` (configurable), `order` (stricter). Symbol allowlist can be configured per-agent session.

**Total agent tools:** 12

---

## 7. API Surface Summary

| API Surface | Count | Primary Entry |
|---|---:|---|
| SDK (BrokerSession) | 27 methods + 6 properties | `from brokers.session import BrokerSession` |
| CLI (Click) | 34 commands | `broker` console script |
| MCP (FastMCP) | 24 tools | `broker-mcp` console script |
| REST (FastAPI) | 97 endpoints | `tradex` → `uvicorn` |
| WebSocket | 3 endpoints | `ws://host/ws/market`, `/ws/replay/{id}` |
| Agent Tools | 12 tools | `interface.agent.tools.AgentTools` |
| **Grand Total** | **197+** | |
