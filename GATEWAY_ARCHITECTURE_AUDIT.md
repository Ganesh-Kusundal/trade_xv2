# Gateway → Factory → Auth → Token Refresh Architecture Audit

## Flow Summary

```
BrokerProviderFactory.create()
  → AuthManager.acquire()           # checks store first, skips if valid
  → DhanHttpClient                  # injects token + refresh callback
  → DhanConnection → BrokerGateway  # facade delegates to adapters
  → TokenRefreshScheduler           # background thread, expired-only
  → HTTP 401 handler                # force_refresh on broker rejection
```

## Token Generation Decision Tree

| Condition | Action | Generates new token? |
|---|---|---|
| `settings.access_token` exists | Use directly | No |
| JSON store has valid JWT | Load from store | No |
| JSON store expired | Call TOTP | Yes |
| Scheduler finds valid state | Skip | No |
| Scheduler finds expired state | Call TOTP | Yes |
| HTTP 401 received | force_refresh | Yes |
| Rate limited (2-min cooldown) | Back off, skip | No |

Key design: `should_generate_token(allow_proactive=False)` in the scheduler ensures TOTP is never called unless the current token is actually expired.

## Exception Hierarchy

```
TradeXV2Error
  └── BrokerError
        ├── RetryableError
        ├── NonRetryableError
        ├── RateLimitError
        ├── CircuitBreakerOpenError
        ├── AuthenticationError
        ├── InstrumentNotFoundError
        ├── OrderError
        ├── NotSupportedError          # replaces NotImplementedError
        │     └── ExitAllError
        ├── BrokerDegradedError
        └── DhanError
              ├── MarketDataError
              ├── ConfigurationError
              ├── DhanIdentityError
              ├── SuperOrderError
              ├── ForeverOrderError
              ├── ConditionalTriggerError
              ├── LedgerError
              ├── UserProfileError
              ├── IPManagementError
              ├── ExitAllError
              └── EDISError
```

`NotSupportedError` is used at broker boundaries instead of `NotSupportedError` (the built-in). This lets callers catch broker-specific unsupported features without catching Python's generic exception.

## Interface Segregation

`MarketDataGateway` composes 8 narrow ISP interfaces:
- MarketDataProvider: history, quote, ltp, depth
- DerivativesProvider: option_chain, future_chain
- BatchMarketDataProvider: ltp_batch, quote_batch, history_batch
- TradingExecutor: place_order, cancel_order, get_orderbook, get_trade_book
- PortfolioReader: positions, holdings, funds, trades
- InstrumentProvider: search, load_instruments
- StreamProvider: stream
- LifecycleAware: describe, capabilities, close

Consumers can depend on the narrow interface instead of the full gateway.

## Facade Pattern

Both gateways are thin facades:
- Dhan.BrokerGateway → DhanConnection → adapters (market_data, orders, options, etc.)
- UpstoxBrokerGateway → UpstoxBroker → adapters (market_data, orders, portfolio, etc.)

No business logic lives in the facade. All state is in the connection/broker layer.

## Test Coverage

| Area | Test File | Status |
|---|---|---|
| Factory auth bootstrap | test_factory_auth.py | 6/6 pass |
| Token reuse vs generation | test_token_bootstrap_policy.py | 2/2 pass |
| HTTP 401 auto-refresh | test_http_client.py | pass |
| Scheduler expired-only refresh | test_token_scheduler.py | pass |
| Scheduler lifecycle start/stop | test_token_scheduler_lifecycle.py | pass |
| Token broadcast to services | test_token_broadcast.py | pass |
| TOTP cooldown enforcement | test_totp_cooldown.py | pass |
| Circuit breaker isolation | test_circuit_breaker_regression.py | pass |
| Full Dhan endpoint verification | verify_dhan_endpoints.py | 22/28 pass (6 pre-existing type-check gaps) |

## Verdict

Architecture is sound. Factory handles token acquisition without redundant generation. AuthManager checks store before calling TOTP. Scheduler only triggers on expiry. HTTP layer auto-refreshes on 401. Exception hierarchy uses proper inheritance from canonical BrokerError base. Interface segregation allows consumers to depend on narrow protocols.
