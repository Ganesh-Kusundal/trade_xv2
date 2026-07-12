# Runtime Flow Diagrams — Part 1

> Sequence diagrams derived from actual source code in `src/`. Each diagram
> uses autonumbering and shows the real call chain with error branches.

---

## 1. System Startup Flow

The full initialization chain from `BrokerSession(broker)` through
`open_session()` to a ready-to-trade `DomainSession`.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant OS as open_session()
    participant Plugin as BrokerPlugin
    participant GW_Factory as bootstrap_gateway()
    participant Adapter as adapter_factory
    participant OMS_Bridge as session_bridge
    participant DS as DomainSession
    participant RB as RuntimeBundle

    Caller->>BS: BrokerSession("dhan", mode="trade")
    BS->>OS: open_session(broker_id, mode, env_path, ...)

    rect rgb(240, 248, 255)
        Note over OS: Phase 1 — Plugin Discovery
        OS->>Plugin: ensure_core_plugins()
        OS->>Plugin: discover_broker_plugins()
        OS->>Plugin: get_broker_plugin(broker_id)
    end

    rect rgb(255, 248, 240)
        Note over OS: Phase 2 — Mode Normalization
        OS->>OS: _normalize_mode(broker_id, mode)
        Note right of OS: Paper: market/trade → sim<br/>Live+sim → ConnectError<br/>Unknown mode → ConnectError
    end

    rect rgb(240, 255, 240)
        Note over OS: Phase 3 — Gateway Bootstrap
        OS->>GW_Factory: bootstrap_gateway(broker_id, require_authenticated=True)
        GW_Factory->>GW_Factory: _create_transport_gateway(broker)
        GW_Factory->>GW_Factory: structural_readiness_probe(gw)
        GW_Factory->>GW_Factory: authenticated_readiness_probe(gw)
        Note right of GW_Factory: On token rejection:<br/>one force-refresh (TOTP)<br/>→ re-probe
        GW_Factory-->>OS: BootstrapResult(READY)
    end

    rect rgb(255, 240, 248)
        Note over OS: Phase 4 — Adapter Wiring
        OS->>Adapter: create_data_adapter(gw, broker_id)
        OS->>Adapter: create_execution_provider(gw, broker_id)
    end

    rect rgb(248, 240, 255)
        Note over OS: Phase 5 — OMS Spine
        alt mode == "trade" with BrokerService
            OS->>OS: runtime.factory.build(broker_service)
        else mode == "trade" standalone
            OS->>OMS_Bridge: build_oms_service(executor, event_bus)
            Note right of OMS_Bridge: Prefers process-wide OMS singleton<br/>Paper: in-memory + fixed capital<br/>Live: requires registered context
        end
    end

    rect rgb(240, 255, 255)
        Note over OS: Phase 6 — Session Assembly
        OS->>DS: DomainSession(provider, event_bus, executor, oms, status)
        DS->>DS: Universe(provider, event_bus, executor, oms)
        OS->>DS: attach_broker_facade(broker_id, extensions)
        OS->>DS: attach_command_dispatcher(dispatcher)
        OS->>DS: attach_query_dispatcher(dispatcher)
        OS->>DS: attach_order_command_fn(closure)
        OS->>DS: InstrumentResolver(known_symbols)
    end

    alt run_selftest == True
        OS->>OS: _run_broker_selftest(session, broker_id)
        Note over OS: Config → Auth → Capabilities<br/>→ Sample Quote → Historical<br/>→ WebSocket → Teardown
    end

    OS-->>BS: DomainSession (ready)
    BS->>RB: RuntimeBundle(session=self._session)
    RB->>RB: ExecutionManager(session)
    RB->>RB: EventBusFacade(event_bus)
    BS->>RB: record_startup()
    Note over RB: Checkpoints: Load Plugin<br/>→ Authenticate → Load Symbol Master<br/>→ Capability Discovery → Warm Cache → Ready
    RB-->>BS: checkpoints (all ok)
    BS-->>Caller: BrokerSession (ready)
```

---

## 2. Broker Connection Flow

Detailed gateway bootstrap from `bootstrap_gateway()` through transport creation,
structural check, auth probe, and TOTP retry.

```mermaid
sequenceDiagram
    autonumber
    participant Caller as open_session()
    participant BG as bootstrap_gateway()
    participant Factory as _create_transport_gateway()
    participant Builder as _create_dhan() / _create_upstox()
    participant Mod as importlib (lazy)
    participant SR as structural_readiness_probe()
    participant Auth as authenticated_readiness_probe()
    participant Probe as execute_read_only_probe()
    participant TOTP as _force_token_refresh()

    Caller->>BG: bootstrap_gateway("dhan", require_authenticated=True)

    rect rgb(240, 248, 255)
        Note over BG: Resolve skip flags
        BG->>BG: skip_probe = skip_auth_probe OR analytics_only OR skip_credential_check
        Note right of BG: require_authenticated=True<br/>→ force probe even with legacy flags
    end

    rect rgb(240, 255, 240)
        Note over BG: Transport Creation
        BG->>Factory: _create_transport_gateway(broker="dhan", env_path, load_instruments, event_bus, lifecycle, risk)
        Factory->>Factory: builder = builders.get("dhan")
        Factory->>Builder: _create_dhan(env_path, ...)
        Builder->>Mod: importlib.import_module("brokers.dhan.identity.factory")
        alt ImportError
            Mod-->>Builder: ModuleNotFoundError
            Builder-->>BG: None
            BG-->>Caller: BootstrapResult(FAILED, "broker package not available")
        else Success
            Mod-->>Builder: module
            Builder->>Builder: BrokerFactory().create(env_path, ...)
            Builder-->>BG: gateway instance
        end
    end

    alt broker in {paper, datalake} OR skip_probe
        BG-->>Caller: BootstrapResult(READY, probe_name="{broker}_skip")
    else Live broker with probe
        rect rgb(255, 248, 240)
            Note over BG: Structural Readiness
            BG->>SR: structural_readiness_probe(gw, "dhan")
            Note right of SR: Checks token present on<br/>connection object (no API call)
            alt struct_ok == False
                SR-->>BG: (False, error)
                BG-->>Caller: BootstrapResult(REAUTH_REQUIRED)
            end
        end

        rect rgb(255, 240, 248)
            Note over BG: Authenticated Probe
            BG->>Auth: authenticated_readiness_probe(gw, "dhan", env_path)
            Auth->>Probe: execute_read_only_probe(gw, "dhan")
            Note right of Probe: Live API call:<br/>dhan → gateway.funds()<br/>upstox → gateway.profile()

            alt probe.ok == True
                Probe-->>Auth: AuthProbeResult(ok=True)
                Auth-->>BG: AuthProbeResult(ok=True)
                BG-->>Caller: BootstrapResult(READY, probe_passed=True)
            else probe.token_rejected == True
                Probe-->>Auth: AuthProbeResult(token_rejected=True)
                rect rgb(255, 255, 230)
                    Note over Auth: TOTP Retry (at most once)
                    Auth->>TOTP: _force_token_refresh(gw, "dhan", env_path)
                    alt refreshed == True
                        Auth->>Probe: execute_read_only_probe(gw, "dhan") [2nd attempt]
                        alt 2nd probe OK
                            Probe-->>Auth: AuthProbeResult(ok=True, refreshed=True)
                            Auth-->>BG: AuthProbeResult(ok=True, refreshed_token=True)
                            BG-->>Caller: BootstrapResult(READY, refreshed_token=True)
                        else 2nd probe fails
                            Probe-->>Auth: AuthProbeResult(ok=False)
                        end
                    else refreshed == False (cooldown/credentials)
                        Auth-->>BG: AuthProbeResult(ok=False, token_rejected=True)
                    end
                end
                BG->>BG: close() gateway (dead gateway cleanup)
                BG-->>Caller: BootstrapResult(REAUTH_REQUIRED)
            else probe other failure
                Probe-->>Auth: AuthProbeResult(ok=False, error)
                Auth-->>BG: AuthProbeResult(ok=False)
                BG->>BG: close() gateway
                BG-->>Caller: BootstrapResult(FAILED)
            end
        end
    end
```

---

## 3. Instrument Resolution Flow

How `BrokerSession.stock("RELIANCE")` resolves a canonical symbol to a
fully-stamped domain `Instrument` with data, execution, and OMS ports.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant DS as DomainSession
    participant Univ as Universe
    participant Inst as Instrument (Equity)
    participant Stamp as _stamp()
    participant Resolver as InstrumentResolver

    Caller->>BS: session.stock("RELIANCE", exchange="NSE")
    BS->>DS: self._session.universe.equity("RELIANCE", "NSE")
    DS->>Univ: equity(symbol="RELIANCE", exchange="NSE")

    rect rgb(240, 248, 255)
        Note over Univ: Phase 1 — Instrument Creation
        Univ->>Inst: Equity("RELIANCE", "NSE", data_provider, execution_provider)
        Note right of Inst: Frozen dataclass with InstrumentId:<br/>symbol="RELIANCE", exchange="NSE"<br/>instrument_type=EQUITY
    end

    rect rgb(240, 255, 240)
        Note over Univ: Phase 2 — Port Stamping (_stamp)
        Univ->>Stamp: _stamp(instrument)
        Stamp->>Inst: _bind_session_ports(data_provider, execution_provider, order_service)
        Note right of Stamp: Stores weak references to:<br/>- DataProvider (quote/history/subscribe)<br/>- ExecutionProvider (place_order)<br/>- OrderServicePort (OMS place/cancel)
    end

    rect rgb(255, 240, 248)
        Note over Univ: Phase 3 — Broker Facade Registration
        alt broker_facade is attached
            Stamp->>Inst: _extensions.register(broker_id, facade)
            Stamp->>Inst: _extensions.register(ext_name, ext) for each extension
        end
    end

    Stamp-->>Univ: Equity (stamped)
    Univ-->>DS: Equity
    DS-->>BS: Equity
    BS-->>Caller: Equity object

    Note over Caller: Later, to get broker-specific IDs:<br/>inst.id → InstrumentId("RELIANCE", "NSE", EQUITY)<br/>inst.broker → facade with broker-specific mappings<br/>inst.capabilities() → [LIMIT, MARKET, SL, ...]
```

---

## 4. Quote Flow

How `BrokerSession.quote(instrument)` pulls a live quote through the
`QuoteManager` → `Instrument.refresh()` → `DataProvider.get_quote()` path.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant QM as QuoteManager
    participant Inst as Instrument
    participant MDP as InstrumentMarketData
    participant Provider as DataProvider
    participant Gateway as Gateway (Dhan/Upstox)

    Caller->>BS: session.quote(inst)
    BS->>QM: self._runtime.quotes.quote(instrument)

    rect rgb(240, 248, 255)
        Note over QM: QuoteManager.quote()
        QM->>Inst: instrument.refresh()
    end

    rect rgb(240, 255, 240)
        Note over Inst: InstrumentMarketData.refresh()
        Inst->>MDP: self.refresh() [mixin method]
        MDP->>MDP: provider = self._resolve_provider()
        Note right of MDP: Resolves DataProvider via<br/>weak reference to session provider
        MDP->>Provider: provider.get_quote(self._id)
        Provider->>Gateway: HTTP GET /quote/{instrument_id}
        Gateway-->>Provider: raw quote response
        Provider-->>MDP: QuoteSnapshot
    end

    rect rgb(255, 248, 240)
        Note over MDP: State Update (thread-safe)
        MDP->>MDP: with self._lock:<br/>self._state = self._state.with_quote(quote)
        Note right of MDP: InstrumentState is immutable;<br/>new copy with updated quote
    end

    MDP-->>Inst: QuoteSnapshot
    Inst-->>QM: QuoteSnapshot
    QM-->>BS: QuoteSnapshot
    BS-->>Caller: QuoteSnapshot

    Note over Caller: QuoteSnapshot contains:<br/>ltp, bid, ask, high, low, open,<br/>close, volume, oi, timestamp
```

---

## 5. History Flow

How `BrokerSession.history(instrument)` retrieves historical OHLCV data
through the `HistoricalManager` → `InstrumentHistory` → `DataProvider` path.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant HM as HistoricalManager
    participant IH as InstrumentHistory
    participant Provider as DataProvider
    participant Gateway as Gateway
    participant Cache as _downloaded cache

    Caller->>BS: session.history(inst, timeframe="1D", days=120)
    BS->>HM: self._runtime.history.series(instrument, timeframe="1D", days=120)

    rect rgb(240, 248, 255)
        Note over HM: HistoricalManager.series()
        HM->>IH: instrument.history(timeframe="1D", days=120)
        Note right of IH: instrument.history returns<br/>InstrumentHistory facade<br/>calling __call__ triggers download
    end

    rect rgb(240, 255, 240)
        Note over IH: InstrumentHistory.download()
        IH->>IH: normalize_timeframe("1D")
        IH->>IH: self._last_params = {timeframe, days, start, end}
        IH->>IH: series = self._fetch(timeframe, days, start, end)

        rect rgb(255, 248, 240)
            Note over IH: _fetch() — Provider Call
            IH->>IH: provider = owner._resolve_provider()
            alt provider.get_history_series() available
                IH->>Provider: provider.get_history_series(id, timeframe, lookback_days)
                Provider->>Gateway: HTTP GET /candles/{id}?tf=1D&days=120
                Gateway-->>Provider: raw OHLCV data
                Provider-->>IH: HistoricalSeries
            else fallback
                IH->>Provider: provider.get_history(id, timeframe, lookback_days)
                Provider->>Gateway: HTTP GET /history/{id}
                Gateway-->>Provider: raw data
                Provider-->>IH: HistoricalSeries (wrapped)
            end
        end

        alt series is None or empty
            IH->>IH: series = HistoricalSeries(bars=[], ...)
        end
        IH->>Cache: self._downloaded = series
        IH->>IH: self._view = None
    end

    IH-->>HM: HistoricalSeries
    HM-->>BS: HistoricalSeries
    BS-->>Caller: HistoricalSeries

    Note over Caller: HistoricalSeries contains:<br/>bars (list of Candle),<br/>coverage, instrument, timeframe,<br/>bar_count property

    Note over Caller: Subsequent calls with same params<br/>return cached _downloaded series.<br/>Call .refresh() to force re-fetch.
```

---

## 6. Subscription Flow

The async subscription lifecycle from `BrokerSession.subscribe()` through
WebSocket connection to live tick delivery via callback.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant SM as SubscriptionManager
    participant Inst as Instrument
    participant StreamMix as InstrumentStreaming
    participant Provider as DataProvider
    participant WS as WebSocket Connection
    participant UserCB as User Callback

    Caller->>BS: session.subscribe(inst, callback=fn)
    BS->>SM: self._runtime.subscriptions.subscribe(instrument, callback, depth=False)

    rect rgb(240, 248, 255)
        Note over SM: SubscriptionManager.subscribe()
        SM->>Inst: instrument.subscribe(callback, depth=False)
    end

    rect rgb(240, 255, 240)
        Note over StreamMix: InstrumentStreaming.subscribe()
        StreamMix->>StreamMix: provider = self._resolve_provider()

        rect rgb(255, 248, 240)
            Note over StreamMix: Build Wrapped Callback
            StreamMix->>StreamMix: def _wrapped(iid, payload):<br/>  update state atomically<br/>  invoke registered tick callbacks<br/>  invoke user callback
        end

        StreamMix->>Provider: provider.subscribe(self._id, _wrapped, depth=False)
        Provider->>WS: WebSocket subscribe(instrument_id)
        Note right of WS: Opens/multiplexes WebSocket<br/>connection to broker<br/>market data endpoint
        WS-->>Provider: SubscriptionHandle
        Provider-->>StreamMix: SubscriptionHandle
    end

    rect rgb(255, 240, 248)
        Note over StreamMix: State Update
        StreamMix->>StreamMix: self._subscription = handle
        StreamMix->>StreamMix: state.with_subscription(<br/>  SubscriptionStatus.SUBSCRIBED,<br/>  started_at=now())
    end

    StreamMix-->>Inst: SubscriptionHandle
    Inst-->>SM: SubscriptionHandle
    SM->>SM: self._handles[str(instrument.id)] = handle
    SM-->>BS: SubscriptionHandle
    BS-->>Caller: SubscriptionHandle

    Note over Caller: SubscriptionHandle has .unsubscribe()

    rect rgb(240, 255, 255)
        Note over WS: Live Data Delivery (async)
        WS-->>Provider: TickPayload (QuoteSnapshot or MarketDepth)
        Provider-->>StreamMix: _wrapped(instrument_id, payload)
        StreamMix->>StreamMix: with self._lock:<br/>state.with_quote(payload) or with_depth(payload)<br/>→ status becomes SUBSCRIBED
        loop Each registered tick callback
            StreamMix-->>UserCB: cb(QuoteSnapshot)
        end
        StreamMix-->>UserCB: callback(instrument_id, payload)
    end

    Note over Caller: Unsubscribe path:
    Caller->>BS: session.unsubscribe(inst)
    BS->>SM: self._runtime.subscriptions.unsubscribe(instrument)
    SM->>SM: handle = self._handles.pop(key)
    SM->>WS: handle.unsubscribe()
    SM->>StreamMix: instrument.unsubscribe()
    StreamMix->>StreamMix: self._subscription.unsubscribe()
    StreamMix->>StreamMix: state.with_unsubscribed()
```

---

## 7. Order Placement Flow (The Critical Path)

The full OMS order lifecycle from `BrokerSession.buy()` through risk checks,
idempotency guard, record-then-submit, ledger outbox, to event publication.
This is the most critical flow in the system.

```mermaid
sequenceDiagram
    autonumber
    participant Caller
    participant BS as BrokerSession
    participant EM as ExecutionManager
    participant DS as DomainSession
    participant CmdDisp as CommandDispatcher
    participant OMS as OmsOrderService
    participant OM as OrderManager
    participant IG as IdempotencyGuard
    participant OV as OrderValidator
    participant RM as RiskManager
    participant LC as OrderLifecycle
    participant LO as LedgerOutbox
    participant ExecProv as ExecutionProvider
    participant EB as EventBus

    Caller->>BS: session.buy(inst, quantity=10, price=2500)
    BS->>EM: self._runtime.execution.buy(inst, 10, 2500, ...)
    EM->>DS: self._session.buy(inst, 10, 2500, ...)
    DS->>DS: _place_order(instrument, Side.BUY, 10, 2500)
    DS->>DS: intent = self.intent(instrument, Side.BUY, 10, 2500)
    Note right of DS: Builds OrderIntent<br/>with auto-generated<br/>correlation_id

    alt _order_command_fn exists (CQRS path)
        DS->>CmdDisp: _order_command_fn(intent)
        CmdDisp->>OMS: OrderCommandHandler → OmsOrderService.place(intent)
    else legacy fallback
        DS->>OMS: place_via_order_service(order_service, intent)
        OMS->>OMS: cmd = _intent_to_command(intent)
    end

    OMS->>OM: order_manager.place_order(cmd, submit_fn)

    rect rgb(255, 240, 240)
        Note over OM: Phase 1 — Idempotency Check (UNDER LOCK)
        OM->>IG: check_and_reserve(lock, orders_by_correlation, correlation_id)
        IG->>IG: with lock:<br/>existing = orders_by_correlation.get(correlation_id)
        alt correlation_id already exists
            alt status == UNKNOWN
                IG-->>OM: ("", OrderResult(error="reconcile before retry"))
            else known status
                IG-->>OM: ("", OrderResult(success=True, existing_order))
            end
            OM-->>Caller: return existing result
        else correlation_id in pending set
            IG-->>OM: ("", OrderResult(error="already in-flight"))
            OM-->>Caller: return error
        else new order
            IG->>IG: pending_correlation.add(correlation_id)
            IG->>IG: order_id = "OM-{uuid}"
            IG-->>OM: (order_id, None)
        end
    end

    rect rgb(240, 255, 240)
        Note over OM: Phase 2 — Validation & Risk (OUTSIDE LOCK)
        OM->>OV: build_and_validate(order_id, request)

        rect rgb(255, 255, 230)
            Note over OV: Placement Gate
            OV->>OV: gate_reason = check_placement_gate()
            alt gate blocks
                OV->>EB: publish(ORDER_REJECTED, reason=gate_reason)
                OV-->>OM: (None, OrderResult(rejected))
            end
        end

        OV->>OV: order = Order(order_id, status=OPEN, ...)

        rect rgb(255, 248, 240)
            Note over OV: Risk Check
            OV->>RM: check_order(order)
            alt risk rejected
                RM-->>OV: RiskResult(allowed=False, reason)
                OV->>EB: publish(RISK_REJECTED, ...)
                OV->>EB: publish(ORDER_REJECTED, ...)
                OV-->>OM: (None, OrderResult(rejected))
            else risk approved
                RM-->>OV: RiskResult(allowed=True)
                OV->>EB: publish(RISK_APPROVED, order_id)
            end
        end
        OV-->>OM: (order, None)
    end

    rect rgb(240, 248, 255)
        Note over OM: Phase 3 — Submit to Broker (Record-then-Submit)
        OM->>LC: submit_to_broker(lock, orders, orders_by_correlation, order, request, submit_fn)

        rect rgb(255, 240, 248)
            Note over LC: Build OrderIntent for ledger
            LC->>LC: intent = OrderIntent(intent_id=order.order_id, ...)
        end

        rect rgb(255, 248, 240)
            Note over LC: Store in book (UNDER LOCK)
            LC->>LC: with lock:<br/>orders[order.order_id] = order<br/>orders_by_correlation[correlation_id] = order
        end

        rect rgb(240, 255, 240)
            Note over LC: Record-then-Submit
            LC->>LO: persist_intent_then_submit(ledger, intent, _broker_submit)
            LO->>LO: ledger.record_intent(intent)
            Note right of LO: Intent durably persisted<br/>BEFORE broker I/O
            LO->>ExecProv: submit_fn(request) → ExecutionProvider.place_order()
            ExecProv-->>LO: Order (from broker)
            LO-->>LC: Order (broker-accepted)
        end

        rect rgb(255, 240, 248)
            Note over LC: Confirm acceptance
            LC->>LO: ledger.record_outcome(SubmissionOutcome.accepted(intent_id))
        end

        alt submit_fn raises exception
            LC->>LC: order = order.with_status(UNKNOWN)
            LC->>LC: with lock:<br/>orders[UNKNOWN] = unknown
            LC->>LO: ledger.record_outcome(SubmissionOutcome.unknown(intent_id, error))
            LC->>EB: publish(ORDER_UPDATED, unknown, reason=error)
            LC-->>OM: (None, OrderResult(UNKNOWN))
            OM->>IG: release_pending(correlation_id)
            OM-->>Caller: OrderResult(UNKNOWN)
        else ledger confirm fails
            LC->>LC: order = order.with_status(UNKNOWN)
            LC->>LC: with lock:<br/>orders[UNKNOWN] = unknown
            LC->>EB: publish(ORDER_UPDATED, unknown, reason="ledger failure")
            LC-->>OM: (None, OrderResult(UNKNOWN))
        end

        LC-->>OM: (order, None)
    end

    rect rgb(240, 255, 255)
        Note over OM: Phase 4 — Record & Publish (UNDER LOCK)
        OM->>LC: record_and_publish(lock, orders, ..., order, request)
        LC->>LC: with lock:<br/>idempotency_guard.release_pending(lock, correlation_id)<br/>orders[order.order_id] = order<br/>orders_by_correlation[correlation_id] = order
        LC->>EB: publish(ORDER_PLACED, order)
    end

    LC-->>OM: (void)
    OM->>OM: metrics.orders_total.inc()
    OM-->>OM: metrics.order_latency.observe(elapsed)
    OM-->>OMS: OrderResult(success=True, order, ACCEPTED)
    OMS-->>Caller: OrderResult (success, order placed)
```

---

## 8. Order Lifecycle State Machine

The canonical order state transitions enforced by `OrderStateValidator`
using `ORDER_STATUS_TRANSITIONS` from `domain/entities/order_lifecycle.py`.
Terminal states are evicted from the `TTLCache` (maxsize=10000, ttl=24h).

```mermaid
sequenceDiagram
    autonumber
    participant OM as OrderManager
    participant LC as OrderLifecycle
    participant SV as OrderStateValidator
    participant SM as StateMachine
    participant Cache as TTLCache
    participant EB as EventBus

    rect rgb(240, 248, 255)
        Note over SV: State Machine Initialization
        OM->>SV: validate_transition(order_id, old_status, new_status)
        SV->>Cache: _state_machines.get(order_id)
        alt no existing machine
            SV->>SM: StateMachine(transitions=ORDER_STATUS_TRANSITIONS, initial=OPEN)
            SV->>Cache: _state_machines[order_id] = new SM
        end
    end

    rect rgb(240, 255, 240)
        Note over SM: Happy Path: Full Lifecycle

        SM-->>SM: OPEN (initial state)

        rect rgb(255, 255, 230)
            Note over SM: Broker confirms placement
            SM->>SV: can_transition_to(OPEN)  [broker reconfirms]
            Note right of SV: OPEN → OPEN = no-op (same status)
        end

        SM->>SM: PARTIALLY_FILLED
        Note right of SM: Partial fill received

        SM->>SM: FILLED
        Note right of SM: Complete fill received
    end

    rect rgb(255, 248, 240)
        Note over SM: Cancellation Branch
        SM-->>SM: OPEN
        SM->>SM: CANCELLED
        Note right of SM: User/system cancel
    end

    rect rgb(255, 240, 240)
        Note over SM: Rejection Branch
        SM-->>SM: OPEN
        SM->>SM: REJECTED
        Note right of SM: Exchange/broker reject
    end

    rect rgb(248, 240, 255)
        Note over SM: Expiry Branch
        SM-->>SM: OPEN
        SM->>SM: EXPIRED
        Note right of SM: GTT/stop expiry
    end

    rect rgb(255, 240, 248)
        Note over SM: Partial Cancel Branch
        SM-->>SM: PARTIALLY_FILLED
        SM->>SM: PARTIALLY_CANCELLED
        Note right of SM: Cancel rest after partial fill
    end

    rect rgb(240, 240, 255)
        Note over SM: UNKNOWN Recovery Branch
        Note over SM: Exception during broker submit<br/>or ledger confirm failure
        SM-->>SM: UNKNOWN
        SM->>SM: OPEN
        Note right of SM: Reconciliation resolves
        SM->>SM: REJECTED
        SM->>SM: CANCELLED
    end

    rect rgb(255, 255, 240)
        Note over Cache: TTLCache Eviction (Terminal States)

        SM->>SM: FILLED / CANCELLED / REJECTED /<br/>PARTIALLY_CANCELLED / EXPIRED
        Note right of SM: Terminal — no further transitions<br/>allowed (empty frozenset)

        rect rgb(240, 255, 255)
            Note over Cache: Memory Management
            Cache->>Cache: maxsize=10,000 orders
            Cache->>Cache: ttl=86,400s (24 hours)
            Note right of Cache: LRU eviction at capacity<br/>TTL eviction after 24h<br/>Terminal orders leave SM in cache<br/>until TTL expires
        end
    end

    rect rgb(255, 240, 240)
        Note over SV: Illegal Transition Handling

        SV->>SM: can_transition_to(target) → False
        alt enforce == True (default)
            SV->>SV: raise IllegalTransitionError(old, new)
            Note right of SV: Order rejected,<br/>book unchanged
        else enforce == False (audit mode)
            SV->>SV: logger.warning("illegal transition ...")
            Note right of SV: Logged but accepted<br/>for observability
        end
    end

    rect rgb(240, 255, 240)
        Note over LC: Upsert from Broker Events

        LC->>LC: upsert_order(lock, orders, ..., order)
        Note right of LC: Called by on_order_update handler<br/>for broker push events
        LC->>SV: validate_transition(order_id, existing.status, new.status)
        alt valid transition
            LC->>LC: store_order(orders, orders_by_correlation, order)
            LC->>EB: publish(ORDER_UPDATED, order)
            alt order.status.is_terminal
                LC->>LC: active_orders.dec()
            end
        else invalid transition
            SV-->>LC: IllegalTransitionError
            Note right of LC: Order update rejected
        end
    end
```

### Transition Table Reference

| Source State | Allowed Targets |
|---|---|
| `OPEN` | PARTIALLY_FILLED, FILLED, CANCELLED, PARTIALLY_CANCELLED, REJECTED, EXPIRED |
| `PARTIALLY_FILLED` | FILLED, CANCELLED, PARTIALLY_CANCELLED, REJECTED |
| `FILLED` | *(terminal)* |
| `CANCELLED` | *(terminal)* |
| `PARTIALLY_CANCELLED` | *(terminal)* |
| `REJECTED` | *(terminal)* |
| `EXPIRED` | *(terminal)* |
| `UNKNOWN` | OPEN, REJECTED, CANCELLED *(reconciliation only)* |
