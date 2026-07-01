# Brokers Module - Implementation Details & Code Examples

## 📋 Detailed Implementation Guide

This document provides **concrete code changes**, migration patterns, and specific examples for implementing the refactoring recommendations from the main audit report.

---

## 🔧 Phase 1: Remove Compatibility Layers (Week 2)

### Change 1.1: Delete MarketDataGatewayAdapter

**Files to DELETE:**
```bash
rm brokers/common/adapters/market_data_gateway_adapter.py
rm brokers/common/adapters/__init__.py
```

**Migration Required:** Update all consumers to use CommonBrokerGateway directly.

**Current Usage Pattern:**
```python
# In bootstrap.py (DELETE THIS FILE TOO)
from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway

adapter = wrap_market_gateway(legacy_gw, broker_id)
```

**New Pattern:**
```python
# Direct usage
gateway = PaperGateway()  # Already implements MarketDataGateway
# But better: Make all gateways implement CommonBrokerGateway directly
```

### Change 1.2: Delete MockBroker

**File to DELETE:**
```bash
rm brokers/paper/mock_broker.py
```

**Migration Required:** Update all tests and CLI code to use PaperGateway directly.

**Current Usage Pattern:**
```python
from brokers.paper.mock_broker import MockBroker, create_demo_broker

broker = MockBroker()
broker.connect()
broker.place_order(...)
```

**New Pattern:**
```python
from brokers.paper import PaperGateway

gateway = PaperGateway()
# No connect() needed - gateway is always "connected"
gateway.place_order(...)

# For demo/test data, add seed methods to PaperGateway directly
# or create test utilities
```

**Action Required:** Move seed methods from MockBroker to PaperGateway or create test utilities.

### Change 1.3: Delete Bootstrap Compatibility

**File to DELETE:**
```bash
rm brokers/common/bootstrap.py
```

**Migration Required:** Update composition root to use BrokerInfrastructure directly.

**Current Usage:**
```python
from brokers.common.bootstrap import create_intelligent_gateway, bootstrap_from_gateways

# Old way
infra = await bootstrap_from_gateways([("dhan", dhan_gw), ("upstox", upstox_gw)])
gateway = await create_intelligent_gateway([("dhan", dhan_gw)])
```

**New Usage:**
```python
from brokers.common.infrastructure import build_infrastructure
from brokers.common.broker_port import CommonBrokerGateway

# All gateways must implement CommonBrokerGateway directly
gateways: list[CommonBrokerGateway] = [dhan_gw, upstox_gw]
infra = await build_infrastructure(gateways, policy=policy)

# For single broker, use gateway directly
result = dhan_gw.ltp("RELIANCE", "NSE")
```

### Change 1.4: Delete async_compat.py

**File to DELETE:**
```bash
rm brokers/common/async_compat.py
```

**Files to UPDATE:**
- `brokers/upstox/websocket/lifecycle_wrapper.py` - Replace async_compat usage
- Any other files importing from async_compat

**Current Usage:**
```python
from brokers.common.async_compat import run_async_compat

# In sync context
result = run_async_compat(coro, fire_and_forget=False)

# In async context  
run_async_compat(coro, fire_and_forget=True)
```

**New Pattern:** Make all code consistently async.

**Migration Strategy:**
1. Make all WebSocket operations async
2. Update all consumers to use async/await
3. Use proper async context management

**Example Migration:**
```python
# OLD (in lifecycle_wrapper.py)
def connect(self) -> None:
    from brokers.common.async_compat import run_async_compat
    run_async_compat(self._mux.connect())

# NEW
async def connect(self) -> None:
    await self._mux.connect()
```

---

## 🔧 Phase 2: Consolidate Gateway Architecture (Week 3-4)

### Change 2.1: Make All Gateways Implement CommonBrokerGateway

**Current State:** All gateways inherit from MarketDataGateway (legacy ABC)
```python
# Dhan
class BrokerGateway(BatchFetchMixin, MarketDataGateway, ObservabilityProvider):

# Upstox  
class UpstoxBrokerGateway(BatchFetchMixin, MarketDataGateway):

# Paper
class PaperGateway(BatchFetchMixin, MarketDataGateway):
```

**New State:** All gateways implement CommonBrokerGateway Protocol
```python
# Dhan
class DhanGateway(CommonBrokerGateway):

# Upstox
class UpstoxGateway(CommonBrokerGateway):  

# Paper
class PaperGateway(CommonBrokerGateway):
```

**Migration Steps:**

#### Step 1: Enhance CommonBrokerGateway Protocol
```python
# In brokers/common/broker_port.py
from typing import Protocol, runtime_checkable
from collections.abc import Sequence
from brokers.common.capabilities import CapabilityDescriptor
from domain.entities import Balance, Order, OrderResponse, Position, Quote, Trade
from domain.entities.market import MarketDepth  
from domain.historical import HistoricalBar, InstrumentRef
from domain.requests import ModifyOrderRequest, OrderRequest

@runtime_checkable
class CommonBrokerGateway(Protocol):
    """The universal broker port - single interface for all broker operations."""
    
    # Lifecycle
    @property
    def broker_id(self) -> str: ...
    
    def list_capabilities(self) -> CapabilityDescriptor: ...
    def supports(self, feature: str) -> bool: ...
    async def close(self) -> None: ...
    def describe(self) -> dict: ...
    
    # Market Data
    async def get_quote_snapshot(self, instrument: InstrumentRef, *, quota: QuotaToken) -> Quote: ...
    async def get_depth_snapshot(self, instrument: InstrumentRef, *, quota: QuotaToken) -> MarketDepth: ...
    async def get_historical_bars(self, request: HistoricalBarRequest, *, quota: QuotaToken) -> Sequence[HistoricalBar]: ...
    
    # Trading
    async def place_order(self, request: OrderRequest, *, quota: QuotaToken) -> OrderResponse: ...
    async def cancel_order(self, order_id: str, *, quota: QuotaToken) -> OrderResponse: ...
    async def modify_order(self, request: ModifyOrderRequest, *, quota: QuotaToken) -> OrderResponse: ...
    async def get_orders(self, *, quota: QuotaToken) -> list[Order]: ...
    async def get_trades(self, *, quota: QuotaToken) -> list[Trade]: ...
    
    # Portfolio
    async def get_positions(self, *, quota: QuotaToken) -> list[Position]: ...
    async def get_margins(self, *, quota: QuotaToken) -> Balance: ...
    
    # Streams
    async def open_market_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle: ...
    async def open_order_stream(self, plan: BrokerStreamPlan) -> BrokerStreamHandle: ...
    async def health(self) -> BrokerHealthSnapshot: ...
```

#### Step 2: Update PaperGateway (Example)
```python
# In brokers/paper/paper_gateway.py

from brokers.common.broker_port import (
    CommonBrokerGateway, 
    BrokerStreamHandle, 
    BrokerStreamPlan, 
    BrokerHealthSnapshot,
    QuotaToken,
    HistoricalBarRequest
)
from brokers.common.capabilities import CapabilityDescriptor
from domain.historical import InstrumentRef
from domain.requests import OrderRequest, ModifyOrderRequest

class PaperGateway(CommonBrokerGateway):
    """Paper trading gateway implementing CommonBrokerGateway Protocol."""
    
    def __init__(self, initial_capital: Decimal = PAPER_INITIAL_CAPITAL) -> None:
        self._market_data = PaperMarketData()
        self._orders = PaperOrders(self._market_data, {})
        self._portfolio = PaperPortfolio(self._orders, initial_capital)
    
    @property 
    def broker_id(self) -> str:
        return "paper"
    
    def list_capabilities(self) -> CapabilityDescriptor:
        from brokers.common.capabilities import CapabilityDescriptor
        return CapabilityDescriptor(
            broker_id="paper",
            supports_place_order=True,
            supports_cancel_order=True,
            # ... other capabilities
        )
    
    def supports(self, feature: str) -> bool:
        return feature in self.list_capabilities().supported_features
    
    # Implement all async methods...
    async def get_quote_snapshot(self, instrument: InstrumentRef, *, quota: QuotaToken) -> Quote:
        # Implementation using existing _market_data
        return self._market_data.quote(instrument.symbol, instrument.exchange)
    
    async def place_order(self, request: OrderRequest, *, quota: QuotaToken) -> OrderResponse:
        # Convert request to parameters and call existing logic
        return self._orders.place_order(
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.transaction_type.value,
            quantity=request.quantity,
            price=request.price,
            order_type=request.order_type.value,
            product_type=request.product_type.value,
            validity=request.validity.value,
            trigger_price=request.trigger_price,
            correlation_id=request.correlation_id,
        )
    
    # ... implement all other methods
```

#### Step 3: Delete MarketDataGateway ABC
```bash
rm brokers/common/gateway.py
```

**Impact:** This removes the legacy interface and forces all brokers to use the new Protocol.

### Change 2.2: Delete gateway_interfaces.py

**File to DELETE:**
```bash
rm brokers/common/gateway_interfaces.py
```

**Migration:** Move any essential SPI ports to appropriate locations.

**Analysis:** This file contains 15+ interfaces that are either:
1. Already duplicated in CommonBrokerGateway
2. Extension-specific (should be in extensions/)
3. Internal implementation details

**Essential Interfaces to Keep:**
- `OrderCommand`, `OrderQuery` → Move to `brokers/common/extensions/order_service.py`
- `PortfolioProvider` → Move to `brokers/common/extensions/portfolio.py`
- Other SPI ports → Move to appropriate extension modules

### Change 2.3: Delete IntelligentMarketDataGateway

**File to DELETE:**
```bash
rm brokers/common/intelligent_market_gateway.py
```

**Migration:** Use BrokerInfrastructure directly.

**Current Usage:**
```python
from brokers.common.intelligent_market_gateway import IntelligentMarketDataGateway

gw = IntelligentMarketDataGateway(infra, smart=True)
result = gw.ltp("NIFTY", "NSE")
```

**New Usage:**
```python
# Use router directly
from brokers.common.infrastructure import BrokerInfrastructure

# For smart routing
result = await infra.router.route("ltp", "NIFTY", "NSE")

# Or use gateway directly for single broker
result = await infra.registry.get_gateway("dhan").get_quote_snapshot(...)
```

---

## 🔧 Phase 3: Simplify Factory Pattern

### Change 3.1: Delete Abstract Factory Interface

**File to DELETE:**
```bash
rm brokers/common/factory.py
```

**Migration:** Use direct constructor calls.

**Current Usage:**
```python
from brokers.common.factory import BrokerProviderFactory
from brokers.dhan.factory import BrokerFactory

factory: BrokerProviderFactory = BrokerFactory()
gateway = factory.create(env_path=env_path, load_instruments=True)
```

**New Usage:**
```python
from brokers.dhan.gateway import DhanGateway

# Direct construction
gateway = DhanGateway.from_config(env_path=env_path, load_instruments=True)
```

### Change 3.2: Simplify Broker Factories

**Files to UPDATE:**
- `brokers/dhan/factory.py`
- `brokers/upstox/factory.py`

**Migration:** Remove BrokerProviderFactory interface implementation.

**Current:**
```python
class BrokerFactory(BrokerProviderFactory):
    def create(self, *, env_path: Path | None = None, ...) -> MarketDataGateway:
        # Complex factory logic
        return gateway
```

**New:**
```python
class DhanGatewayFactory:
    """Factory for creating DhanGateway instances."""
    
    @staticmethod
    def create(
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        lifecycle: LifecycleManager | None = None,
    ) -> DhanGateway:
        # Simplified factory logic
        return DhanGateway(
            config_path=env_path,
            load_instruments=load_instruments,
            event_bus=event_bus,
            risk_manager=risk_manager,
            lifecycle=lifecycle,
        )
```

---

## 🔧 Phase 4: Clean Up Extensions

### Change 4.1: Consolidate Extension System

**Files to DELETE:**
```bash
rm -rf brokers/common/api/
```

**Migration:** Move SPI ports to extension modules.

**Current Structure:**
```
brokers/common/api/
├── __init__.py          # Re-exports
├── spi.py              # BrokerSource enum
└── tests/
```

**New Structure:**
```
brokers/common/extensions/
├── __init__.py          # Extension registry
├── order_service.py    # OrderCommand, OrderQuery
├── portfolio.py        # PortfolioProvider  
├── market_intelligence.py
└── ...
```

### Change 4.2: Simplify Extension Registry

**Current:** Complex extension system with bundles and registry.

**Simplification:** Use Protocol-based service discovery.

```python
# Simplified extension system
from typing import Protocol, runtime_checkable

@runtime_checkable
class OrderService(Protocol):
    def place_order(self, request: OrderRequest) -> OrderResponse: ...
    def cancel_order(self, order_id: str) -> bool: ...

@runtime_checkable  
class PortfolioService(Protocol):
    def get_positions(self) -> list[Position]: ...
    def get_funds(self) -> Balance: ...

# Extension registry
class ExtensionRegistry:
    def __init__(self) -> None:
        self._services: dict[type, dict[str, object]] = {}
    
    def register(self, service_type: type, broker_id: str, instance: object) -> None:
        if not isinstance(instance, service_type):
            raise TypeError(f"{instance} does not implement {service_type}")
        
        if service_type not in self._services:
            self._services[service_type] = {}
        self._services[service_type][broker_id] = instance
    
    def get(self, service_type: type, broker_id: str) -> object:
        return self._services.get(service_type, {}).get(broker_id)
    
    def get_required(self, service_type: type, broker_id: str) -> object:
        service = self.get(service_type, broker_id)
        if service is None:
            raise LookupError(f"No {service_type} registered for {broker_id}")
        return service
```

---

## 🔧 Phase 5: Remove Dead Code

### Change 5.1: Remove NotImplementedError Methods

**Files to UPDATE:** All gateway implementations.

**Pattern to Remove:**
```python
# REMOVE THIS
def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
    raise NotImplementedError(f"{type(self).__name__} does not support modify_order")
```

**Replacement:**
1. If the broker supports the operation: Implement it properly
2. If the broker doesn't support it: Remove it from the interface

**Example:** PaperGateway currently doesn't support modify_order. Either:
1. **Implement it:** Add modify_order support to PaperOrders
2. **Remove from interface:** If modify_order is not essential for paper trading

### Change 5.2: Remove Duplicate Imports and Unused Code

**Pattern to Look For:**
```python
# CHECK FOR THESE PATTERNS
import unused_module          # Import but never used
from some.module import UnusedClass  # Unused import

class UnusedClass:            # Class never instantiated
    pass

def unused_function():       # Function never called
    pass

# OLD_pattern = "something"    # Constant never used
```

**Tools to Use:**
```bash
# Run static analysis
pylint brokers/ --disable=all --enable=unused-import,unused-variable,unused-argument
pyflakes brokers/
```

---

## 🧪 Test Refactoring

### Tests to DELETE:
```bash
rm brokers/common/tests/test_market_data_gateway_adapter.py
rm brokers/common/tests/test_async_compat.py
rm brokers/paper/tests/test_paper.py  # Keep useful parts, delete MockBroker tests
```

### Tests to UPDATE:
- All tests that use MockBroker → Use PaperGateway directly
- All tests that use async_compat → Make tests async
- All tests that use MarketDataGatewayAdapter → Test direct gateway usage

### Example Test Migration:

**OLD Test:**
```python
# In test_market_data_gateway_adapter.py
def test_adapter_creation():
    from brokers.common.adapters.market_data_gateway_adapter import wrap_market_gateway
    from brokers.paper import PaperGateway
    
    gateway = PaperGateway()
    adapter = wrap_market_gateway(gateway, "paper")
    
    assert adapter.broker_id == "paper"
    assert isinstance(adapter, CommonBrokerGateway)
```

**NEW Test:**
```python
# Direct test of PaperGateway
def test_paper_gateway_as_common_broker():
    from brokers.paper import PaperGateway
    from brokers.common.broker_port import CommonBrokerGateway
    
    gateway = PaperGateway()
    
    # PaperGateway should directly implement CommonBrokerGateway
    assert isinstance(gateway, CommonBrokerGateway)
    assert gateway.broker_id == "paper"
```

---

## 📊 Migration Checklist

### Phase 1: Compatibility Layer Removal
- [ ] Delete `market_data_gateway_adapter.py`
- [ ] Delete `mock_broker.py`
- [ ] Delete `bootstrap.py`
- [ ] Delete `async_compat.py`
- [ ] Update all consumers to use new patterns
- [ ] Run full test suite

### Phase 2: Gateway Architecture Consolidation  
- [ ] Enhance CommonBrokerGateway Protocol
- [ ] Update PaperGateway to implement CommonBrokerGateway
- [ ] Update Dhan Gateway to implement CommonBrokerGateway
- [ ] Update Upstox Gateway to implement CommonBrokerGateway
- [ ] Delete MarketDataGateway ABC (`gateway.py`)
- [ ] Delete gateway_interfaces.py
- [ ] Delete IntelligentMarketDataGateway
- [ ] Run full test suite

### Phase 3: Factory Simplification
- [ ] Delete abstract factory interface
- [ ] Simplify broker factories
- [ ] Update composition root
- [ ] Run full test suite

### Phase 4: Extension Consolidation
- [ ] Delete brokers/common/api/ directory
- [ ] Move SPI ports to extensions/
- [ ] Simplify extension registry
- [ ] Run full test suite

### Phase 5: Dead Code Removal
- [ ] Remove NotImplementedError methods
- [ ] Remove unused imports and classes
- [ ] Remove commented-out code
- [ ] Remove obsolete TODOs
- [ ] Run static analysis tools
- [ ] Run full test suite

### Phase 6: Final Validation
- [ ] Comprehensive integration testing
- [ ] Performance benchmarking
- [ ] Error handling validation
- [ ] Documentation updates

---

## 🚨 Common Migration Issues & Solutions

### Issue 1: Sync vs Async Boundary
**Problem:** Some code expects sync methods, new interface is async.

**Solution:** Make all broker code async throughout. Update consumers to use async/await.

### Issue 2: Method Signature Mismatches  
**Problem:** Old interface uses positional args, new interface uses typed requests.

**Solution:** Use adapter functions temporarily, then migrate to new signatures.

```python
# Temporary adapter
async def place_order_async(gateway: CommonBrokerGateway, *, symbol: str, exchange: str = "NSE", 
                          side: str = "BUY", quantity: int = 1) -> OrderResponse:
    from domain.requests import OrderRequest
    from domain.enums import Side, OrderType, ProductType, Validity
    
    request = OrderRequest(
        symbol=symbol,
        exchange=exchange,
        transaction_type=Side(side),
        quantity=quantity,
        order_type=OrderType.MARKET,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
    )
    return await gateway.place_order(request, quota=quota)
```

### Issue 3: Missing QuotaToken Requirements
**Problem:** New interface requires QuotaToken, old code doesn't have it.

**Solution:** Add quota management to all consumers.

```python
# In application code
from brokers.common.quota_scheduler import QuotaScheduler

quota_scheduler = QuotaScheduler()

async def get_ltp(symbol: str, exchange: str = "NSE") -> Decimal:
    quota_token = quota_scheduler.acquire("dhan", "ltp", "MARKET_DATA")
    try:
        gateway = infra.registry.get_gateway("dhan")
        quote = await gateway.get_quote_snapshot(InstrumentRef(symbol, exchange), quota=quota_token)
        return quote.ltp
    finally:
        quota_scheduler.release(quota_token)
```

### Issue 4: Property vs Method Access
**Problem:** Old code uses properties, new interface uses methods.

**Solution:** Update all property access to method calls.

```python
# OLD
positions = gateway.positions()

# NEW  
positions = await gateway.get_positions(quota=quota_token)
```

---

## 🎯 Success Validation Checklist

### After Each Phase:
- [ ] All existing tests pass (or are updated appropriately)
- [ ] No import errors
- [ ] No type checking errors
- [ ] All broker integrations work
- [ ] Performance metrics are acceptable

### Final Validation:
- [ ] Code reduction target met (≥30%)
- [ ] Interface count reduced (15+ → 2-3)
- [ ] No compatibility layers remain
- [ ] Architecture is simpler and more maintainable
- [ ] All business functionality preserved
- [ ] Error handling is comprehensive
- [ ] Documentation is updated

---

## 📈 Expected Benefits

### Code Metrics Improvements:
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total Lines | ~12,000+ | ~8,000- | -33% |
| Interface Count | 15+ | 2-3 | -85% |
| File Count | 521+ | ~400- | -23% |
| Cyclomatic Complexity | High | Medium | -40% |

### Quality Metrics Improvements:
| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Type Safety | Medium | High | +2x |
| Test Maintainability | Medium | High | +2x |
| Developer Onboarding | Weeks | Days | -80% |
| New Broker Integration | Days | Hours | -90% |

---

## 🔗 Additional Files to Review

The following files contain additional refactoring opportunities:

### High Priority:
- `brokers/common/resilience/` - Multiple resilience implementations
- `brokers/dhan/resilience/` - Dhan-specific resilience  
- `brokers/upstox/resilience/` - Upstox-specific resilience
- `brokers/common/auth/` - Authentication patterns
- `brokers/dhan/auth/` - Dhan authentication
- `brokers/upstox/auth/` - Upstox authentication

### Medium Priority:
- `brokers/common/connection/` - Connection management
- `brokers/dhan/connection.py` - Dhan connection
- `brokers/upstox/broker.py` - Upstox broker facade
- `brokers/common/observability/` - Monitoring
- `brokers/dhan/metrics.py` - Dhan metrics
- `brokers/upstox/metrics.py` - Upstox metrics

### Low Priority:
- `brokers/dhan/instruments/` - Instrument handling
- `brokers/upstox/instruments/` - Instrument handling
- `brokers/dhan/websocket/` - WebSocket implementations
- `brokers/upstox/websocket/` - WebSocket implementations

---

## Conclusion

This implementation guide provides **concrete, actionable steps** to refactor the brokers module for v1. The migration is substantial but achievable through systematic, phased implementation.

**Key Success Factor:** Maintain working state after each phase by ensuring comprehensive test coverage and careful migration of consumers.

**Estimated Timeline:** 4-6 weeks for full implementation with a team of 2-3 developers.

**Estimated Impact:** 30-40% code reduction, significantly improved maintainability, better type safety, and easier future development.