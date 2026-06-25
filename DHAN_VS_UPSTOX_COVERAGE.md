# Dhan vs Upstox Gateway Coverage Audit

## ABC Compliance

Both `Dhan.BrokerGateway` and `UpstoxBrokerGateway` implement all 23 abstract methods from `MarketDataGateway`. Zero missing on either side.

## Extra Methods Beyond ABC

| Method | Dhan | Upstox |
|---|---|---|
| `depth_20` | ✅ | ❌ |
| `depth_200` | ✅ | ❌ |
| `modify_order` | ✅ | ✅ |
| `get_order` | ✅ | ✅ |
| `unstream` | ✅ | ✅ |
| `get_connection_status` | ✅ | ❌ |
| `get_circuit_breaker_states` | ✅ | ❌ |
| `get_token_refresh_metrics` | ✅ | ❌ |
| `get_rate_limiter_metrics` | ✅ | ❌ |

## ObservabilityProvider

- **Dhan**: implements it (connection status, circuit breaker states, token refresh metrics, rate limiter metrics)
- **Upstox**: does NOT implement it

## Extended Capabilities

| Capability | Dhan | Upstox |
|---|---|---|
| Super orders | ✅ | ❌ |
| Forever orders (GTT) | ✅ | ✅ |
| Conditional triggers | ✅ | ✅ |
| EDIS | ✅ | ❌ |
| Exit all | ✅ | ✅ |
| Margin calculator | ✅ | ✅ |
| Kill switch | ✅ | ✅ |
| Slice order | ✅ | ✅ |
| IP management | ✅ | ✅ |
| Ledger | ✅ | ✅ |
| User profile | ✅ | ✅ |
| Order validation | ✅ | ❌ |
| Expired options data | ✅ | ❌ |
| IPO | ❌ | ✅ |
| Mutual funds | ❌ | ✅ |
| Payments/payouts | ❌ | ✅ |
| Fundamentals (P&L, balance sheet) | ❌ | ✅ |
| Cover orders | ❌ | ✅ |
| Multi-order | ❌ | ✅ |
| News | ❌ | ✅ |
| Market status | ❌ | ✅ |
| Smartlist | ❌ | ✅ |
| FII/DII data | ❌ | ✅ |
| OI/PCR/Max Pain | ❌ | ✅ |
| Option Greeks (dedicated API) | ❌ | ✅ |
| Portfolio stream | ❌ | ✅ |
| Webhooks | ❌ | ✅ |
| Session risk | ❌ | ✅ |

## Capability Manifest: Broker-Specific Gaps

### Dhan-Only (4 capabilities)
- `extended.super_orders` — bracket orders
- `extended.edis` — e-DIS authorization
- `capability.order_stream` — dedicated order WebSocket
- `capability.level2_market_data` — depth 20/200 feeds

### Upstox-Only (17 capabilities)
- `extended.gtt_order` — Good Till Triggered orders
- `extended.cover_order` — cover orders
- `extended.ipo` — IPO subscriptions
- `extended.mutual_funds` — MF orders
- `extended.payments` — fund withdrawals
- `extended.fundamentals` — company financials
- `capability.news` — market news feed
- `capability.market_status` — exchange status
- `capability.multi_order` — batch order placement
- `capability.session_risk` — risk management
- `capability.smartlist` — curated instrument lists
- `capability.fii_dii` — institutional flow data
- `capability.oi_pcr_maxpain` — options analytics
- `capability.market_intelligence` — aggregated intel
- `capability.webhooks` — push notifications
- `capability.portfolio_stream` — portfolio WebSocket
- `capability.option_greeks` — dedicated Greeks API

### Shared (35 capabilities)
All core trading, market data, derivatives, portfolio, and lifecycle capabilities.

### Neither (15 capabilities)
TLS, MTF, global markets, volatility index, monitoring, scanner, backtest, replay, analytics, portfolio summary, symbols, strategy — these are either app-layer features or not broker-provided.

## Key Gaps to Address

### Dhan missing from Upstox
1. `depth_20` / `depth_200` — Upstox has no 20/200-level depth WebSocket
2. `ObservabilityProvider` — Upstox gateway lacks connection/circuit breaker/refresh metrics
3. Super orders (bracket orders) — Dhan-native, no Upstox equivalent
4. EDIS — Dhan-specific, no Upstox equivalent

### Upstox missing from Dhan
1. GTT orders — Upstox has full CRUD, Dhan has "forever orders" (similar but different API)
2. Cover orders — Dhan has no cover order support
3. Multi-order — Dhan has no batch order API
4. IPO — Dhan has no IPO endpoint
5. Mutual funds — Dhan has no MF endpoint
6. Fundamentals — Dhan has no financial statements API
7. News — Dhan has no news endpoint
8. Market status — Dhan has no dedicated status API
9. Smartlist — Dhan has no curated instrument lists
10. FII/DII — Dhan has no institutional flow data
11. OI/PCR/Max Pain — Dhan has no options analytics endpoints
12. Option Greeks (dedicated) — Dhan provides Greeks via option chain only
13. Portfolio stream — Dhan has order stream but not portfolio-level stream
14. Webhooks — Dhan has no webhook support
15. Session risk — Dhan has no session-level risk management

## Recommendations

### Priority 1: Add ObservabilityProvider to Upstox
The Upstox gateway should implement `ObservabilityProvider` for parity. It has HTTP client and WebSocket infrastructure that could expose connection status, circuit breaker states, and token refresh metrics.

### Priority 2: Add depth_20/depth_200 to Upstox (if API supports)
Check if Upstox API provides 20+ level depth data. If so, implement `depth_20` and `depth_200` methods on the Upstox gateway.

### Priority 3: Map equivalent capabilities
- Dhan "forever orders" ≈ Upstox "GTT orders" — already mapped in manifest
- Dhan "conditional triggers" ≈ Upstox "alerts" — already mapped
- Dhan "exit all" ≈ Upstox "exit all" — already mapped

### Priority 4: Document broker-specific features
Clearly document which features are broker-specific so users know what they get with each broker.
