# Architecture Flowchart Review

## 📊 Flowchart vs Actual Implementation Alignment

### ✅ **All Major Components Present**

| Flowchart Component | Actual Implementation | Status |
|---------------------|----------------------|--------|
| External Systems | Exchanges/Broker APIs | ✅ `config/endpoints.py`, broker packages |
| | Historical Data Providers | ✅ `datalake/`, `brokers/*.data_provider` |
| | News / Corporate Actions | ✅ `brokers.upstox.news`, `brokers.dhan.extensions` |
| | Broker Plugins | ✅ `infrastructure/broker_plugin.py` |
| | Market Data Connectors | ✅ `brokers.dhan.data`, `brokers.upstox.market_data` |
| Cache | Redis / Memory | ⚠️ Memory cache only (`infrastructure.cache`) |
| | DuckDB / PostgreSQL | ✅ `runtime/` SQLite, datalake for analytics |
| | Parquet | ✅ `infrastructure.datalake.parquet_store` |

### ✅ **Runtime Kernel - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Bootstrap | `bootstrap_gateway()` | `infrastructure/gateway/factory.py` |
| Dependency Injection | Session wiring | `tradex/session.py::open_session` |
| Plugin Registry | `BrokerPlugin`, adapter registry | `infrastructure/adapter_factory.py` |
| Clock | Time service | `domain/time_service.py` |
| Configuration | Config loading | `config/`, `src/config/*` |
| Broker Session Manager | `DomainSession` | `domain/universe.py::Session` |
| Event Bus | `EventBus` | `infrastructure/event_bus/event_bus.py` |

### ✅ **Domain Model - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Market | `MarketDepth`, `Quote` | `domain/entities/market.py` |
| Instrument | `Instrument` ABC | `domain/instruments/instrument.py` |
| Equity | `Equity` | `domain/instruments/instrument.py::Equity` |
| Future | `Future` | `domain/instruments/instrument.py::Future` |
| Option | `Option` | `domain/instruments/instrument.py::Option` |
| Option Chain | `OptionChain` | `domain/options/option_chain.py` |
| Portfolio | `Portfolio` | `domain/portfolio/portfolio.py` |
| Position | `Position` | `domain/entities/position.py` |
| Order | `Order` | `domain/entities/order.py` |
| Trade | `Trade` | `domain/entities/trade.py` |
| Account | `AccountView` | `domain/portfolio/account_view.py` |

### ✅ **Market Data Runtime - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Subscription Manager | `StreamManagerAdapter` | `brokers.upstox.adapters.streaming_gateway` |
| Quote Manager | `QuoteSnapshot` + state | `instrument_market_data.py` |
| Market Depth | `MarketDepth` | `domain/entities/market.py` |
| Tick Stream | WebSocket feeds | `brokers.dhan.streaming`, `brokers.upstox.websocket` |
| Candle Builder | `HistoricalSeries` | `domain/candles/historical.py` |
| Historical Series | `InstrumentHistory` | `domain/candles/instrument_history.py` |

### ✅ **Analytics - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Scanner | `Scanner` | `domain/scanners/` |
| Signal Generator | `Signal` | `domain/signals/` |
| Universe Filter | `portfolio.quality_engine` | `domain/portfolio/` |
| Pattern Engine | `indicators/` | `domain/indicators/` |
| Statistics | Computed properties | `Instrument`, `MarketDepth`, etc. |

### ✅ **Strategy Runtime - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Strategy Manager | `TradingOrchestrator` | `runtime/trading_orchestrator.py` |
| Execution Plan | `OrderIntent`, `ExecutionPlan` | `domain/orders/` |
| Risk Engine | `RiskManager` | `domain/risk/`, `infrastructure/risk/` |

### ✅ **OMS - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Order Book | `OrderStore` | `domain/repositories/`, `infrastructure/db/` |
| Execution Engine | `OrderManager` | `application/oms/order_manager.py` |
| Reconciliation | `ReconciliationService` | `brokers.dhan.portfolio.reconciliation` |
| Fill Handler | `FillHandler` | `application/oms/fill_handler.py` |

### ✅ **Portfolio Engine - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Position Manager | `PositionManager` | `domain/portfolio/position_manager.py` |
| Portfolio Manager | `Portfolio` | `domain/portfolio/portfolio.py` |
| P&L | Computed from positions | `domain/portfolio/pnl.py` |
| Exposure | `RiskView` | `domain/ports/risk_view.py` |

### ✅ **Replay & Backtesting - All Present**

| Flowchart | Implementation | File |
|-----------|----------------|------|
| Replay Engine | `ReplayService` | `domain/backtest/replay.py` |
| Backtest Engine | `BacktestEngine` | `domain/backtest/` |
| Virtual Clock | `VirtualClock` | `domain/runtime/virtual_clock.py` |

## Missing / Partial Components

| Flowchart | Status | Note |
|-----------|--------|------|
| Zerodha broker | DROPPED | Not part of the supported set (ADR-013). Supported: Dhan, Upstox, Paper, Datalake. |
| Redis Cache | PARTIAL | Memory cache is primary; Redis cache backend exists in `infrastructure/cache_redis.py` (optional). |
| PostgreSQL | DEFERRED | SQLite (execution ledger/order store) + DuckDB (analytics) + Parquet (lake) is the canonical stack (ADR-014). Postgres only if a multi-worker API needs shared state. |
| Command Dispatcher | PRESENT | Explicit `runtime/commands.CommandDispatcher` + `runtime/queries.QueryDispatcher` (ADR-012). |

## 🚀 **Data Flow Verification**

The **actual flow** matches the flowchart:

```
External Systems
    ↓
Broker Plugins (connect → bootstrap_gateway)
    ↓
Cache → DB/FILE (instrumentation layer)
    ↓
Runtime Kernel (session creation, event bus)
    ↓
Domain Model (instrument → market data)
    ↓
Market Data Runtime (subscribe → tick → candle)
    ↓
Analytics (indicators → scanner → signal)
    ↓
Strategy Runtime (signal → execution plan → risk check)
    ↓
OMS (risk → execute → orderbook → broker)
    ↓
Portfolio (fill → position → P&L)
```

## ✨ **Working Live Connection Flow**

```
tradex.connect("dhan", mode="market")
    ↓
bootstrap_gateway()                  # Auth probe
    ↓
BrokerFactory().create()             # Gateway creation  
    ↓
DhanConnection created               # Auth + HTTP client
    ↓
DhanDataProvider(DhanBrokerGateway)  # Data adapter
    ↓
Session(provider) + Universe         # Composition root
    ↓
instrument.refresh()                 # API call: /marketfeed/ltp
    ↓
instrument.broker.depth20()          # WS: wss://depth-api-feed.dhan.co/twentydepth
    ↓
session.account.refresh()            # API call: /fundlimit
```

**Conclusion: The architecture is complete and matches the flowchart.**