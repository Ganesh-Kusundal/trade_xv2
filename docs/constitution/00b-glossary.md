# 00b — Ubiquitous Language / Glossary

**Status:** Canonical  
**Rule:** Every module, doc, and API MUST use these terms with these meanings. Synonym forks require an ADR-level rename.

---

## Market & Instruments

### Asset
A tradable financial instrument class (equity, future, option, commodity). Identified by asset class + underlying, not by venue symbol alone.

### Exchange
A regulated marketplace where instruments are listed and traded (e.g. NSE, BSE, MCX). Owns trading calendar, session hours, and segment rules.

### Market
An operational trading context: exchange + segment + session type (e.g. NSE cash regular session). Determines calendar, tick size, and margin rules.

### Instrument
The platform's canonical representation of something tradable. Combines symbol identity, exchange, segment, expiry/strike (if derivative), and tick/lot metadata. **Instrument is the aggregate root for tradability metadata.**

### Symbol
A human or broker-facing string identifier for an instrument (e.g. `RELIANCE`, `NIFTY24JULFUT`). Symbols are **not** canonical identity — they map to Instrument via normalization rules.

### Contract
A derivative instrument with defined expiry, strike, and option type. A Contract is a specialized Instrument.

---

## Data

### Tick
A single price/volume update at a point in time. Immutable once emitted.

### Candle (Bar)
An OHLCV aggregate over a time window (1m, 5m, daily, …). Built from ticks or sourced from history provider.

### Session (Market Session)
A contiguous period within a trading day when a market accepts orders (pre-open, regular, post-close). Distinct from **Runtime Session** (below).

---

## Strategy & Analytics

### Indicator
A computed time series derived from market data (SMA, RSI, ATR, …). Pure function of inputs + parameters; no side effects.

### Strategy
A ruleset or model that consumes indicators and/or market data and produces **Signals**. Strategy code is identical across all execution targets.

### Signal
An immutable intent to act: direction, instrument, quantity hint, confidence, timestamp, strategy attribution. **A Signal is not an Order.** Risk converts eligible Signals to Orders.

### Feature
A transformed data point in the feature pipeline (may feed indicators or strategies directly).

---

## Trading

### Order
An instruction to buy or sell an instrument at specified terms (type, quantity, price, TIF). Managed by OMS through a strict FSM. Identified by platform `correlation_id` + broker `order_id` after submission.

### Fill
A partial or complete execution of an Order at a price and quantity. Fills update Position and Portfolio. Immutable once recorded.

### Execution
The act of matching an Order against a venue or simulator. **Execution** is the process; **Fill** is the outcome record.

### Position
Net open quantity (+ direction) for an Instrument in an Account. Derived from fills; reconciled against broker truth in Live mode.

### Exposure
Risk measure: capital at risk from open positions and pending orders. Used by Risk gate pre-trade checks.

### Portfolio
The collection of Positions, cash, and PnL for an Account at a point in time. Portfolio is read-optimized; Position is write path.

---

## Runtime & Capabilities

### Runtime Session
An operator-initiated platform instance: config profile, active broker plugin, active execution target, and wired kernel components. Distinct from **Market Session**.

### Execution Target
The capability adapter at the end of the pipeline that fulfills Orders. Implementations: **Replay**, **Backtest**, **Paper**, **Live Broker**. Same OMS and Risk upstream; only the target adapter differs.

### Replay
Deterministic re-execution of historical market data through the full kernel (indicators → strategy → risk → OMS → simulated target). Uses injected clock; event stream reproducible.

### Backtest
Batch evaluation of a strategy over historical data. Produces equity curve, trade journal, and metrics. Uses Backtest execution target.

### Paper
Simulated live trading: real-time market data, simulated fills through OMS. Uses Paper execution target. Zero-parity with Replay on fill semantics.

### Live (Live Broker Execution)
Real venue submission via broker plugin. Optional capability; same kernel, additional operational requirements (auth, reconcile, durable idempotency).

### Broker
A plugin providing market data access and (when Live is enabled) order submission to a specific broker API (Dhan, Upstox, Paper).

### Account
The trading account at a broker: buying power, holdings, and order authority scope.

---

## Cross-Cutting

### Event
An immutable domain message published on the EventBus (e.g. `ORDER_PLACED`, `FILL_RECEIVED`, `SIGNAL_GENERATED`). Events are the integration contract between contexts.

### Correlation ID
Platform-generated idempotency key for an Order intent. Duplicate place with same correlation_id must not double-submit.

---

## Term Relationships

```text
Exchange ──lists──▶ Instrument ◀──maps── Symbol
                        │
                        ├──▶ Contract (if derivative)
                        │
Market Data ──▶ Feature ──▶ Indicator ──▶ Strategy ──▶ Signal
                                                        │
                                                        ▼
                                              Risk ──▶ Order ──▶ Execution Target
                                                        │              │
                                                        ▼              ▼
                                                     Fill ──▶ Position ──▶ Portfolio
```

---

## Forbidden Synonyms

| Do not use | Use instead |
|---|---|
| Trade (as noun for order) | Order or Fill (be specific) |
| Position size (ambiguous) | Quantity or Exposure |
| Sim / Simulation mode (ambiguous) | Replay, Backtest, or Paper (specific target) |
| Broker order (redundant) | Order (broker_id is metadata) |
| Strategy signal / alert | Signal |
| Session (unqualified) | Runtime Session or Market Session |
