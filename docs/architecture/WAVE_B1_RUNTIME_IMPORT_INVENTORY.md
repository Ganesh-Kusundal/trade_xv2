# Wave B1 — `tradex.runtime` Production Import Inventory

**Scope:** production (non-test) imports under `application/` and `infrastructure/`  
**Method:** facade docstring / star-re-export targets under `tradex/runtime/`  
**Status:** inventory only — **no migrations applied**  
**Date:** 2026-07-10

## Summary

| Area | Production files with real imports | Import statements (approx.) |
|------|------------------------------------|-----------------------------|
| `application/` | 13 | ~45 |
| `infrastructure/` | 19 | ~50 |
| **Excluded** | Docstring-only / comment-only mentions; `**/tests/**` | — |

### Docstring-only (not migration work)

These *mention* `tradex.runtime` only in usage docs or comments — no executable import:

| File | Note |
|------|------|
| `application/services/download_engine.py` | Usage docstring |
| `application/services/data_validator.py` | Usage docstring |
| `application/services/instrument_registry.py` | Usage docstring |
| `application/execution/submission_pipeline.py` L20 | Usage docstring (`build_payload`); **L44 `dtos` is real** |
| `infrastructure/config/settings.py` L11 | Usage docstring; **L70 `env_loader` is real** |
| `infrastructure/observability/{alerting,health_check,audit}.py` | Usage docstrings only |
| `infrastructure/pool/connection_pool.py` | Usage docstring only |
| `infrastructure/broker_infrastructure.py` L11–12 | Usage docstring; **L34–42 are real** |
| `infrastructure/*/\__init__.py` comments `# moved from tradex.runtime` | Comments only |

### Layering caution (application)

Several application modules import facades whose **canonical** home is `infrastructure.*` (notably `observability.audit`, `ssl_hardening`, `resilience.errors`, `clock`). Blind rewrite to infrastructure would **break** the import-linter contract *Application infrastructure separation*. Prefer:

- domain ports / domain errors when available
- application-local modules when the facade points back into application
- keep thin runtime facades only where app↛infra must stay forbidden

---

## Facades with real logic (not pure re-export)

| Module | Status | Notes |
|--------|--------|-------|
| `tradex.runtime.extensions.registry` | **REAL LOGIC** | ExtensionBundle / ExtensionRegistry / factory registry — kernel still lives in runtime |
| `tradex.runtime.extensions` (`__init__`) | Re-export of registry | Canonical docstring points at `tradex.runtime.extensions.registry` (not domain/infra) |
| `tradex.runtime.factory` | **REAL LOGIC** | `BrokerProviderFactory` ABC (not pure star re-export) |
| `tradex.runtime.capabilities` | Dual pure re-export | `brokers.common.broker_capabilities` + `domain.value_objects.capability` — no local logic |
| `tradex.runtime.adapters.__init__` | Thin runtime-internal re-export | Re-exports sibling facade, not infrastructure |
| `tradex.runtime.stream_orchestrator` | Mostly pure | Star from `application.streaming.orchestrator` + extra `_parse_exchange_time` from `tick_router` |
| `infrastructure.resilience.errors` | **REAL LOGIC + re-exports** | Domain error re-exports **plus** `convert_network_errors` decorator |
| `tradex.runtime.__init__` | Aggregator facade | Re-exports sibling runtime modules |

Most other `tradex/runtime/**` modules matching this inventory are pure `from <canonical> import *` facades.

---

## Rewrite table — APPLICATION (priority 1)

| file | old import | proposed new import | notes |
|------|------------|---------------------|-------|
| `application/services/__init__.py` | `from tradex.runtime.services.data_validator import …` | `from application.services.data_validator import …` | Circular package init via facade; import siblings |
| `application/services/__init__.py` | `from tradex.runtime.services.download_engine import …` | `from application.services.download_engine import …` | same |
| `application/services/__init__.py` | `from tradex.runtime.services.historical_data import …` | `from application.services.historical_data import …` | same |
| `application/services/__init__.py` | `from tradex.runtime.services.instrument_registry import …` | `from application.services.instrument_registry import …` | same |
| `application/services/__init__.py` | `from tradex.runtime.services.production_readiness import …` | `from application.services.production_readiness import …` | same |
| `application/services/production_readiness.py` | `from tradex.runtime.resilience.errors import TradeXV2Error` | `from domain.exceptions import TradeXV2Error` | Facade → `infrastructure.resilience.errors` → domain; **prefer domain** to avoid app→infra |
| `application/services/production_readiness.py` | `from tradex.runtime.ssl_hardening import assert_secure_session` | `from infrastructure.security.ssl_hardening import assert_secure_session` | Facade canonical; **layer risk** app→infra — may need port/indirection |
| `application/scheduling/quota_scheduler.py` | `from tradex.runtime.broker_port import QuotaToken` | `from domain.ports.broker_gateway import QuotaToken` | pure facade |
| `application/scheduling/quota_scheduler.py` | `from tradex.runtime.capabilities import RateLimitProfile` | `from brokers.common.broker_capabilities import RateLimitProfile` | dual facade; **layer risk** app→brokers.common |
| `application/scheduling/quota_scheduler.py` | `from tradex.runtime.errors import QuotaExhaustedError` | `from domain.errors import QuotaExhaustedError` | pure facade |
| `application/scheduling/quota_scheduler.py` | `from tradex.runtime.observability.audit import emit_quota_event` (×2 lazy) | `from infrastructure.observability.audit import emit_quota_event` | Facade canonical; **layer risk** app→infra — keep facade or move audit hooks to application |
| `application/data/provenance.py` | `from tradex.runtime.clock import time_service` | `from infrastructure.time.clock import time_service` | Facade canonical; **layer risk** app→infra |
| `application/data/historical_coordinator.py` | `from tradex.runtime.broker_port import HistoricalBarRequest, QuotaToken` | `from domain.ports.broker_gateway import …` | pure facade |
| `application/data/historical_coordinator.py` | `from tradex.runtime.errors import MergeConflictError, RoutingError` | `from domain.errors import MergeConflictError, RoutingError` | pure facade |
| `application/data/historical_coordinator.py` | `from tradex.runtime.models import OperationKind, RouteDecision, RoutingRequest` | `from domain.models.routing import …` | pure facade |
| `application/data/historical_coordinator.py` | `from tradex.runtime.provenance import BarRangeRecord, ChunkRecord, ConflictRecord, ProvenanceLedger` | `from application.data.provenance import …` | Self-facade cycle; local sibling |
| `application/data/historical_coordinator.py` | `from tradex.runtime.registry import BrokerRegistry` | `from application.composer.registry import BrokerRegistry` | pure facade |
| `application/data/historical_coordinator.py` | `from tradex.runtime.router import BrokerRouter` | `from application.composer.router import BrokerRouter` | pure facade |
| `application/data/historical_coordinator.py` | `from tradex.runtime.observability.audit import emit_merge_conflict` / `emit_historical_chunk` | `from infrastructure.observability.audit import …` | **layer risk** app→infra |
| `application/streaming/candle_aggregator.py` | `from tradex.runtime.stream_orchestrator import MarketTick` | `from application.streaming.orchestrator import MarketTick` | type-only; defined in orchestrator |
| `application/streaming/orchestrator.py` | `from tradex.runtime.observability.audit import emit_stream_state_change` | `from infrastructure.observability.audit import emit_stream_state_change` | **layer risk** app→infra |
| `application/oms/reconciliation/__init__.py` | `from tradex.runtime.reconciliation.engine import ReconciliationEngine` | `from application.oms.reconciliation.engine import ReconciliationEngine` | Self-facade cycle |
| `application/composer/execution.py` | `from tradex.runtime.models import OperationKind, RoutingRequest` (×2) | `from domain.models.routing import OperationKind, RoutingRequest` | pure facade |
| `application/composer/registry.py` | `from tradex.runtime.extensions import ExtensionRegistry` | **Keep** `tradex.runtime.extensions` **or** `tradex.runtime.extensions.registry` | Facade has **real logic**; no non-runtime canonical yet |
| `application/composer/factory.py` (TYPE_CHECKING) | `tradex.runtime.broker_port.CommonBrokerGateway` | `domain.ports.broker_gateway.CommonBrokerGateway` | |
| `application/composer/factory.py` (TYPE_CHECKING) | `tradex.runtime.historical_coordinator.HistoricalDataCoordinator` | `application.data.historical_coordinator.HistoricalDataCoordinator` | |
| `application/composer/factory.py` (TYPE_CHECKING) | `tradex.runtime.infrastructure.BrokerInfrastructure` | `infrastructure.broker_infrastructure.BrokerInfrastructure` | **layer risk** in TYPE_CHECKING only |
| `application/composer/factory.py` (TYPE_CHECKING) | `tradex.runtime.policy.SourceSelectionPolicy` | `domain.policies.source_selection.SourceSelectionPolicy` | |
| `application/composer/factory.py` (TYPE_CHECKING) | `tradex.runtime.quota_scheduler.QuotaScheduler` | `application.scheduling.quota_scheduler.QuotaScheduler` | |
| `application/composer/factory.py` | `from tradex.runtime.historical_coordinator import HistoricalQuery` | `from application.data.historical_coordinator import HistoricalQuery` | runtime import |
| `application/composer/factory.py` | `from tradex.runtime.historical_coordinator import HistoricalDataCoordinator` | `from application.data.historical_coordinator import HistoricalDataCoordinator` | in `create_composers` |
| `application/composer/factory.py` | `from tradex.runtime.policy_defaults import default_source_selection_policy` | `from domain.policies.defaults import default_source_selection_policy` | |
| `application/composer/factory.py` | `from tradex.runtime.quota_scheduler import QuotaScheduler as QuotaSchedulerCls` | `from application.scheduling.quota_scheduler import QuotaScheduler as QuotaSchedulerCls` | |
| `application/composer/factory.py` | `from tradex.runtime.registry import BrokerRegistry` | `from application.composer.registry import BrokerRegistry` | |
| `application/composer/factory.py` | `from tradex.runtime.router import BrokerRouter` | `from application.composer.router import BrokerRouter` | |
| `application/composer/factory.py` | `from tradex.runtime.stream_orchestrator import StreamOrchestrator` | `from application.streaming.orchestrator import StreamOrchestrator` | |
| `application/composer/market_data.py` (TYPE_CHECKING) | `tradex.runtime.historical_coordinator…` | `application.data.historical_coordinator…` | |
| `application/composer/market_data.py` (TYPE_CHECKING) | `tradex.runtime.provenance.ProvenanceLedger` | `application.data.provenance.ProvenanceLedger` | |
| `application/composer/market_data.py` (TYPE_CHECKING) | `tradex.runtime.stream_orchestrator…` | `application.streaming.orchestrator…` | |
| `application/execution/submission_pipeline.py` | `from tradex.runtime.dtos import BrokerOrderPayload` | `from domain.models.dtos import BrokerOrderPayload` | pure facade |

---

## Rewrite table — INFRASTRUCTURE (priority 2)

| file | old import | proposed new import | notes |
|------|------------|---------------------|-------|
| `infrastructure/session/infra.py` | `from tradex.runtime.policy_defaults import default_source_selection_policy` | `from domain.policies.defaults import default_source_selection_policy` | |
| `infrastructure/session/infra.py` | `from tradex.runtime.quota_scheduler import QuotaScheduler` | `from application.scheduling.quota_scheduler import QuotaScheduler` | **layer risk** infra→application |
| `infrastructure/session/infra.py` | `from tradex.runtime.registry import BrokerRegistry` | `from application.composer.registry import BrokerRegistry` | **layer risk** infra→application |
| `infrastructure/session/infra.py` | `from tradex.runtime.router import BrokerRouter` | `from application.composer.router import BrokerRouter` | **layer risk** infra→application |
| `infrastructure/auth/totp_cooldown.py` | `from tradex.runtime.resilience.errors import TradeXV2Error` | `from domain.exceptions import TradeXV2Error` *(or `infrastructure.resilience.errors`)* | Prefer domain base |
| `infrastructure/auth/totp_cooldown.py` | `from tradex.runtime.auth.metrics import AuthMetrics` (×2 lazy) | `from infrastructure.auth.metrics import AuthMetrics` | sibling; break self-facade cycle |
| `infrastructure/auth/token_persistence.py` | `from tradex.runtime.auth.jwt_expiry import JwtExpiry` | `from infrastructure.auth.jwt_expiry import JwtExpiry` | sibling |
| `infrastructure/auth/token_persistence.py` | `from tradex.runtime.auth.token import TokenSource, TokenState, TokenStateStore` | `from infrastructure.auth.token import …` | sibling |
| `infrastructure/auth/token_persistence.py` | `from tradex.runtime.auth.env_token import update_env_token` | `from infrastructure.auth.env_token import update_env_token` | sibling lazy |
| `infrastructure/auth/token_ensure.py` | `from tradex.runtime.auth.metrics import AuthMetrics` | `from infrastructure.auth.metrics import AuthMetrics` | sibling |
| `infrastructure/auth/token_ensure.py` | `from tradex.runtime.auth.token import …` | `from infrastructure.auth.token import …` | sibling |
| `infrastructure/auth/token_ensure.py` | `from tradex.runtime.auth.token_persistence import …` | `from infrastructure.auth.token_persistence import …` | sibling |
| `infrastructure/auth/token_ensure.py` | `from tradex.runtime.auth.token_policy import should_generate_token` | `from infrastructure.auth.token_policy import should_generate_token` | sibling |
| `infrastructure/auth/token_ensure.py` | `from tradex.runtime.auth.totp_cooldown import TotpRateLimitError` | `from infrastructure.auth.totp_cooldown import TotpRateLimitError` | sibling |
| `infrastructure/auth/credential_validator.py` | `from tradex.runtime.auth.credential_resolver import CredentialResolver` | `from infrastructure.auth.credential_resolver import CredentialResolver` | sibling |
| `infrastructure/auth/credential_resolver.py` | `from tradex.runtime.env_loader import load_env_file` | `from infrastructure.config.env_loader import load_env_file` | |
| `infrastructure/auth/token_policy.py` | `from tradex.runtime.auth.token import TokenState` | `from infrastructure.auth.token import TokenState` | sibling |
| `infrastructure/gateway/base.py` | `from tradex.runtime.capabilities import BrokerCapabilities` | `from brokers.common.broker_capabilities import BrokerCapabilities` | dual facade half |
| `infrastructure/gateway/factory.py` | `from tradex.runtime.connection.bootstrap_result import structural_readiness_probe` | `from infrastructure.connection.bootstrap_result import structural_readiness_probe` | sibling package |
| `infrastructure/gateway/factory.py` | `from tradex.runtime.connection.authenticated_readiness import authenticated_readiness_probe` | `from infrastructure.connection.authenticated_readiness import authenticated_readiness_probe` | sibling package |
| `infrastructure/observability/http_server.py` | `from tradex.runtime.build_info import build_info_dict` | `from infrastructure.build_info import build_info_dict` | |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.broker_port import CommonBrokerGateway` | `from domain.ports.broker_gateway import CommonBrokerGateway` | |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.capabilities import BrokerCapabilities` | `from brokers.common.broker_capabilities import BrokerCapabilities` | |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.extensions import ExtensionBundle, ExtensionRegistry` | **Keep** `tradex.runtime.extensions` | real logic in runtime |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.historical_coordinator import HistoricalDataCoordinator` | `from application.data.historical_coordinator import HistoricalDataCoordinator` | **layer risk** infra→app |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.policy import SourceSelectionPolicy` | `from domain.policies.source_selection import SourceSelectionPolicy` | |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.quota_scheduler import QuotaScheduler` | `from application.scheduling.quota_scheduler import QuotaScheduler` | **layer risk** infra→app |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.registry import BrokerRegistry` | `from application.composer.registry import BrokerRegistry` | **layer risk** infra→app |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.router import BrokerRouter` | `from application.composer.router import BrokerRouter` | **layer risk** infra→app |
| `infrastructure/broker_infrastructure.py` | `from tradex.runtime.stream_orchestrator import StreamOrchestrator` | `from application.streaming.orchestrator import StreamOrchestrator` | **layer risk** infra→app |
| `infrastructure/adapters/extensions.py` | `from tradex.runtime.extensions import ExtensionBundle, get_extension_factory` | **Keep** `tradex.runtime.extensions` | real logic |
| `infrastructure/adapters/extensions.py` | `from tradex.runtime.gateway import MarketDataGateway` | `from infrastructure.gateway.base import MarketDataGateway` | |
| `infrastructure/adapters/market_data_gateway_adapter.py` | `from tradex.runtime.adapters.historical_mapper import dataframe_to_historical_bars` | `from infrastructure.adapters.historical_mapper import dataframe_to_historical_bars` | sibling |
| `infrastructure/adapters/market_data_gateway_adapter.py` | `from tradex.runtime.broker_port import …` | `from domain.ports.broker_gateway import …` | |
| `infrastructure/adapters/market_data_gateway_adapter.py` | `from tradex.runtime.capabilities import BrokerCapabilities, CapabilityDescriptor` | `from brokers.common.broker_capabilities import …` | |
| `infrastructure/adapters/market_data_gateway_adapter.py` | `from tradex.runtime.gateway import MarketDataGateway` | `from infrastructure.gateway.base import MarketDataGateway` | |
| `infrastructure/common_broker_access.py` | `from tradex.runtime.adapters.market_data_gateway_adapter import …` | `from infrastructure.adapters.market_data_gateway_adapter import …` | sibling package |
| `infrastructure/common_broker_access.py` | `from tradex.runtime.broker_port import CommonBrokerGateway` | `from domain.ports.broker_gateway import CommonBrokerGateway` | |
| `infrastructure/common_broker_access.py` | `from tradex.runtime.gateway import MarketDataGateway` | `from infrastructure.gateway.base import MarketDataGateway` | |
| `infrastructure/batch_mixin.py` | `from tradex.runtime.batch_executor import batch_execute` | `from infrastructure.batch_executor import batch_execute` | |
| `infrastructure/config/settings.py` | `from tradex.runtime.env_loader import load_env_file` | `from infrastructure.config.env_loader import load_env_file` | sibling |
| `infrastructure/connection/authenticated_readiness.py` | `from tradex.runtime.auth.credential_resolver import CredentialResolver` | `from infrastructure.auth.credential_resolver import CredentialResolver` | |
| `infrastructure/connection/authenticated_readiness.py` | `from tradex.runtime.auth.metrics import AuthMetrics` | `from infrastructure.auth.metrics import AuthMetrics` | |
| `infrastructure/connection/authenticated_readiness.py` | `from tradex.runtime.auth import JsonTokenStateStore` | `from infrastructure.auth import JsonTokenStateStore` *(or `…token`)* | package facade → infra.auth |
| `infrastructure/connection/authenticated_readiness.py` | `from tradex.runtime.auth.token_persistence import TokenPersistence` | `from infrastructure.auth.token_persistence import TokenPersistence` | |
| `infrastructure/resilience/rate_limiter.py` | `from tradex.runtime.auth.metrics import AuthMetrics` | `from infrastructure.auth.metrics import AuthMetrics` | |

### Already migrated (no action)

| file | note |
|------|------|
| `infrastructure/retry.py` | Now imports `infrastructure.resilience.*` directly (sibling agent) |

---

## Recommended Wave B1 rewrite order

1. **Safe domain rewrites (no layer risk):** `broker_port`, `errors`, `models`, `dtos`, `policy`, `policy_defaults` → `domain.*`
2. **Application self-facades:** `services/*`, `provenance`, `reconciliation`, `quota_scheduler`, `historical_coordinator`, `stream_orchestrator`, `registry`, `router` → `application.*`
3. **Infrastructure self-facades / siblings:** `auth.*`, `connection.*`, `gateway`, `adapters.*`, `env_loader`, `build_info`, `batch_executor`, `ssl_hardening` → `infrastructure.*`
4. **Hold / design decision:**
   - `tradex.runtime.extensions` (real logic — extract later)
   - Cross-layer edges: app→`observability.audit` / `ssl_hardening` / `clock`; infra→`application.composer|scheduling|streaming|data`
5. **Capabilities split:** map symbols to `brokers.common.broker_capabilities` vs `domain.value_objects.capability`

## Unique old → new module map (facade docstring)

| old (`tradex.runtime…`) | proposed canonical |
|-------------------------|-------------------|
| `.broker_port` | `domain.ports.broker_gateway` |
| `.errors` | `domain.errors` |
| `.models` | `domain.models.routing` |
| `.dtos` | `domain.models.dtos` |
| `.policy` | `domain.policies.source_selection` |
| `.policy_defaults` | `domain.policies.defaults` |
| `.capabilities` | **split:** `brokers.common.broker_capabilities` + `domain.value_objects.capability` |
| `.resilience.errors` | `infrastructure.resilience.errors` *(errors themselves: `domain.errors` / `domain.exceptions`)* |
| `.resilience.backoff` | `infrastructure.resilience.backoff` |
| `.resilience.circuit_breaker` | `infrastructure.resilience.circuit_breaker` |
| `.resilience.rate_limiter` | `infrastructure.resilience.rate_limiter` |
| `.ssl_hardening` | `infrastructure.security.ssl_hardening` |
| `.clock` | `infrastructure.time.clock` |
| `.observability.audit` | `infrastructure.observability.audit` |
| `.observability.health_check` | `infrastructure.observability.health_check` |
| `.build_info` | `infrastructure.build_info` |
| `.env_loader` | `infrastructure.config.env_loader` |
| `.settings` | `infrastructure.config.settings` |
| `.gateway` | `infrastructure.gateway.base` |
| `.connection.*` | `infrastructure.connection.*` |
| `.auth.*` | `infrastructure.auth.*` |
| `.batch_executor` | `infrastructure.batch_executor` |
| `.connection_pool` | `infrastructure.pool.connection_pool` |
| `.infrastructure` | `infrastructure.broker_infrastructure` |
| `.adapters.*` | `infrastructure.adapters.*` |
| `.services.*` | `application.services.*` |
| `.historical_coordinator` | `application.data.historical_coordinator` |
| `.provenance` | `application.data.provenance` |
| `.quota_scheduler` | `application.scheduling.quota_scheduler` |
| `.stream_orchestrator` | `application.streaming.orchestrator` |
| `.registry` | `application.composer.registry` |
| `.router` | `application.composer.router` |
| `.reconciliation.engine` | `application.oms.reconciliation.engine` |
| `.submission_pipeline` | `application.execution.submission_pipeline` |
| `.extensions` | **still** `tradex.runtime.extensions.registry` (real logic) |
