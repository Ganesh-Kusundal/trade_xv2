# CQRS Adoption — Current Status

> Last updated: 2026-07-10
> Scope: Adopt the proposed Trading OS architecture (CQRS Command/Query
> Dispatchers, diagram reconciliation, resilience subsystem) into `Trade_XV2`.

## Summary

The proposed Trading OS diagram was already ~90% implemented in `Trade_XV2`.
This work closed the three real gaps (no formal CQRS dispatchers, persistence
mislabeled, Zerodha phantom) and made two under-stated strengths explicit
(resilience subsystem, composition-root kernel). All code is written and
statically reviewed; **the test suite and import-linter have NOT been executed**
(the terminal was unavailable during implementation).

## What was delivered

### P0 — Architecture decisions (docs)
| Artifact | Location | Status |
|---|---|---|
| ADR-012 CQRS dispatchers | `docs/architecture/adrs/adr-012-cqrs.md` | ✅ |
| ADR-013 Broker set (drop Zerodha) | `docs/architecture/adrs/adr-013-brokers.md` | ✅ |
| ADR-014 Persistence (SQLite+DuckDB+Parquet) | `docs/architecture/adrs/adr-014-persistence.md` | ✅ |
| Diagram reconciliation | `examples/ARCHITECTURE_REVIEW.md` (updated table) | ✅ |
| Runtime Kernel doc | `docs/architecture/RUNTIME_KERNEL.md` | ✅ |

### P1 — CQRS dispatcher package
| Component | Location | Status |
|---|---|---|
| `Command` / `CommandResult` / `PlaceOrderCommand` / `SubscribeInstrumentCommand` / `LoadHistoryCommand` | `src/runtime/commands/command.py` | ✅ |
| `CommandDispatcher` (sync, correlation + event publish) | `src/runtime/commands/dispatcher.py` | ✅ |
| `OrderCommandHandler` / `SubscribeCommandHandler` / `HistoryCommandHandler` | `src/runtime/commands/handlers.py` | ✅ |
| `Query` / `QueryResult` / `PortfolioQuery` / `CandleQuery` | `src/runtime/queries/query.py` | ✅ |
| `QueryDispatcher` (read-only) | `src/runtime/queries/dispatcher.py` | ✅ |
| `PortfolioQueryHandler` / `CandleQueryHandler` | `src/runtime/queries/handlers.py` | ✅ |
| import-linter "Dispatcher broker isolation" contract | `pyproject.toml` | ✅ |

### P2 — Dispatcher wiring into the composition root
- `tradex/session.py` (`open_session`) builds `CommandDispatcher` + `QueryDispatcher`
  and attaches them to `DomainSession`.
- `domain/universe.py` (`Session`): `attach_command_dispatcher`,
  `attach_query_dispatcher`, `command_dispatcher` / `query_dispatcher` properties.
  `domain` does NOT import `runtime` (Domain independence preserved).

### P3 — Orchestrator routes via dispatcher
- `application/trading/trading_orchestrator.py`: accepts an injected
  `order_command_fn` closure; `_execute_signal` → `_place_order` routes through it.
- `runtime/trading_runtime_factory.py`: builds the `CommandDispatcher` + closure
  and injects it. The orchestrator never imports `runtime.commands` (no
  `application → runtime` cycle).

### P4 — Zerodha drop, ResilienceConfig, Runtime Kernel doc
- Zerodha marked DROPPED in `examples/ARCHITECTURE_REVIEW.md` (ADR-013 already).
- `runtime/resilience.py`: `ResilienceConfig` dataclass (frozen) + `from_env()`.
- `runtime/trading_runtime_factory.py`: accepts `resilience`, gates parity check,
  exposes it on `Runtime`.

### Follow-up #2 — SDK/CLI/API actually use the dispatcher
- `domain/universe.py` (`Session.place`): routes an `OrderIntent` through an
  injected `order_command_fn` closure; falls back to OMS path.
- `tradex/session.py`: builds the `OrderIntent → PlaceOrderCommand →
  CommandResult → OrderResult` closure and attaches via `attach_order_command_fn`.
- So `session.place()` / `buy()` / `limit()` now flow through the `CommandDispatcher`.

### Follow-up #3 — Subscribe/History handlers registered
- `SubscribeCommandHandler` / `HistoryCommandHandler` updated to the real
  `DataProvider` API (`subscribe(instrument_id, callback, *, depth)`,
  `history_batch(...)`).
- `tradex/session.py` registers both against the session `DataProvider` when present.
- `CandleQueryHandler` registration is gated on `QueryExecutor.get_candles`
  existing (avoids a latent `AttributeError`).

### Follow-up #4 — ResilienceConfig applied to collaborators
- `infrastructure/bootstrap.py`: `build_event_bus` / `build_async_event_bus` /
  `build_resilient_event_bus` / `build_production_event_bus` accept `resilience`
  and apply `event_log_enabled`, `idempotency_ttl_seconds` (→ bus cache size),
  `max_async_bus_queue` (→ `AsyncEventBus` queue).
- `interface/ui/services/broker_service.py` and `runtime/composition.py` build the
  bus via `ResilienceConfig.from_env()`.

## Tests written (not yet executed)
| Test file | Covers |
|---|---|
| `tests/unit/runtime/test_dispatchers.py` | Dispatcher routing, unknown-type errors, no-event-on-failure, query read-only, `PlaceOrderCommand` adaptation |
| `tests/unit/runtime/test_dispatcher_wiring.py` | Orchestrator routes via closure; `Session` exposes dispatchers; `Session.place` routes via closure; subscribe/history via `DataProvider` |
| `tests/unit/runtime/test_resilience_config.py` | `ResilienceConfig` defaults + `from_env` |
| `tests/unit/infrastructure/test_resilient_bus.py` | `ResilienceConfig` drives `EventBus` / `AsyncEventBus` construction |

## Outstanding / deferred
1. **Execute the test suite + import-linter.** Blocked by unavailable terminal
   during implementation. This is the single highest-priority open item.
2. **`ResilienceConfig.idempotency_backend` not yet wired into the OMS.** The OMS
   uses its in-process `IdempotencyGuard`; the Redis/file `IdempotencyService` is
   a separate, currently-unwired component. Deliberately deferred (ponytail: no
   speculative wiring without a caller).
3. **No separate event-sourced projection store** for queries (reused managers —
   correct, per ADR-012).
4. **No async command bus** (kept sync for deterministic critical path — correct).
5. **No PostgreSQL migration** (deferred to a real multi-worker need — ADR-014).

## How to validate (when terminal is available)
```bash
cd /Users/apple/Downloads/Trade_XV2
python -m pytest tests/unit/runtime/ tests/unit/infrastructure/test_resilient_bus.py -q
# import-linter per pyproject.toml (confirms "Dispatcher broker isolation" + existing contracts)
```

## Layering invariants preserved (verified statically)
- `domain` does not import `runtime` / `infrastructure` / `application`
  ("Domain independence" contract).
- `application` does not import `runtime` in a way that creates a reverse cycle
  (orchestrator uses an injected closure, not `runtime.commands`).
- `runtime.commands` / `runtime.queries` do not import `brokers.*`
  ("Dispatcher broker isolation" contract).
- `runtime` does not import `interface` ("Runtime does not import interface").
