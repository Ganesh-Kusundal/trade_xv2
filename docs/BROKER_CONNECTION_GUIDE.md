# Broker Connection Guide

## Quick Start

### Test Connection

```bash
# Test both brokers
PYTHONPATH=/workspace python scripts/test_broker_connection.py

# Test specific broker
PYTHONPATH=/workspace python scripts/test_broker_connection.py --broker dhan
PYTHONPATH=/workspace python scripts/test_broker_connection.py --broker upstox
```

### Expected Output

```
============================================================
DHAN BROKER CONNECTION TEST
============================================================
✅ Gateway created via factory
✅ Connection status: Connected
✅ Funds: ₹0.34 available
✅ Positions: 0 open positions
✅ Orders: 0 pending orders

🎉 DHAN CONNECTION SUCCESSFUL
```

## Architecture

### Standard Factory Pattern

The system uses a **Factory Pattern** for broker integration. You should NEVER instantiate broker connections directly.

**❌ Wrong (Direct Instantiation):**
```python
from brokers.dhan.gateway import DhanConnection
conn = DhanConnection(client_id="...", api_key="...")  # WRONG!
```

**✅ Correct (Factory Pattern):**
```python
from brokers.dhan.factory import BrokerFactory
from pathlib import Path

factory = BrokerFactory()
gateway = factory.create(
    env_path=Path('.env.local'),
    load_instruments=False
)
# Gateway is now fully configured with auth, HTTP client, resolver, etc.
```

### Why Factory?

The `BrokerFactory` handles:
1. **Settings Loading**: Reads from `.env.local` securely
2. **Authentication**: Manages TOTP, token refresh, JWT validation
3. **Dependency Injection**: Creates HTTP client, symbol resolver, event bus
4. **Rate Limiting**: Configures API rate limiters
5. **Circuit Breakers**: Sets up failure handling
6. **Token Scheduling**: Auto-refreshes tokens before expiry

## Configuration

### Environment Variables (.env.local)

```bash
# Dhan Configuration
DHAN_CLIENT_ID=your_client_id
DHAN_API_KEY=your_api_key
DHAN_PIN=your_pin
DHAN_TOTP_SECRET=your_totp_secret
DHAN_ENV=LIVE  # or TEST

# Upstox Configuration  
UPSTOX_API_KEY=your_api_key
UPSTOX_API_SECRET=your_api_secret
UPSTOX_REDIRECT_URI=your_redirect_uri
UPSTOX_ENV=LIVE  # or TEST
```

## Available Gateway Methods

Once you have a gateway instance:

```python
# Account Info
funds = gateway.funds()              # Balance and margins
positions = gateway.positions()      # Open positions
holdings = gateway.holdings()        # Holdings portfolio

# Orders
orders = gateway.get_orderbook()     # All orders
order = gateway.get_order(id)        # Specific order
trades = gateway.get_trade_book()    # Executed trades

# Market Data
quote = gateway.quote(symbol)        # LTP quote
depth = gateway.depth(symbol)        # Market depth
history = gateway.history(...)       # Historical candles

# Trading
order_id = gateway.place_order(...)  # Place new order
gateway.modify_order(...)            # Modify existing
gateway.cancel_order(...)            # Cancel order

# Status
status = gateway.get_connection_status()  # Connection health
metrics = gateway.get_rate_limiter_metrics()  # Rate limit status
```

## Troubleshooting

### "No module named 'brokers'"

**Solution:** Set PYTHONPATH
```bash
export PYTHONPATH=/workspace:$PYTHONPATH
# Or run with: PYTHONPATH=/workspace python ...
```

### "Missing client_id argument"

**Cause:** Trying to instantiate `DhanConnection` directly instead of using factory.

**Solution:** Use `BrokerFactory.create()` as shown above.

### Rate Limit Errors

Expected during testing. The system has built-in rate limiting:
- Token generation: Limited by broker API
- Order placement: Circuit breaker after failures
- Market data: Cooldown periods

Wait for cooldown or check metrics:
```python
metrics = gateway.get_rate_limiter_metrics()
print(f"Rate limit state: {metrics}")
```

### Connection Status Empty `{}`

An empty dict `{}` from `get_connection_status()` means **connected successfully**.
The method only returns data when there are issues to report.

## Testing Checklist

Before live trading:

- [ ] Run `test_broker_connection.py` successfully
- [ ] Verify funds match broker app
- [ ] Verify positions match broker app  
- [ ] Test order placement in sandbox/test mode
- [ ] Verify WebSocket market data streaming
- [ ] Check rate limiter metrics are healthy
- [ ] Confirm circuit breakers are closed (not tripped)

## Security Notes

- ✅ Credentials stored in `.env.local` (gitignored)
- ✅ Tokens auto-refreshed via TOTP (no hardcoded tokens)
- ✅ Rate limiters prevent API abuse
- ✅ Circuit breakers protect against cascading failures
- ❌ Never commit `.env.local` to git
- ❌ Never log raw API keys or tokens
