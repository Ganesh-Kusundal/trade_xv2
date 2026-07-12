# Runtime Flow Diagrams — Part 2

> Sequences 9–15 covering position updates, strategy pipeline, replay/backtest,
> WebSocket reconnection, graceful shutdown, and recovery.

---

## 9. Position Update Flow

Traces the full path from a broker FILL event through the EventBus to the
`PositionManager`, the VWAP average-price computation inside `Position.with_fill`,
and the downstream `PortfolioContext` mirror.

```mermaid
sequenceDiagram
    autonumber
    participant Broker as Broker WS
    participant EventBus as EventBus
    participant PM as PositionManager
    participant Guard as ReentrancyGuard
    participant Idempotency as IdempotencyCache
    participant Project as project_trade()
    participant Pos as Position.with_fill
    participant StateMachine as StateMachine
    participant Ctx as PortfolioContext
    participant Risk as RiskManager

    Broker->>EventBus: TRADE_APPLIED event (verified by OMS)
    EventBus->>PM: on_trade_applied(event)
    PM->>Guard: _reentrancy_guard()
    Guard-->>PM: not reentered
    PM->>Idempotency: check trade_id in processed_set
    alt Duplicate trade_id
        Idempotency-->>PM: already processed → skip
    else New trade
        Idempotency-->>PM: ok → add to set + LRU deque
        PM->>PM: apply_trade(trade)
        Note over PM: Acquire RLock for thread safety
        PM->>PM: Get current Position by (exchange, symbol)
        PM->>Project: project_trade(current, trade)
        Project->>Pos: current.with_fill(signed_qty, price)
        Note over Pos: VWAP avg_price computation:<br/>If flat → use fill_price<br/>If adding → (cur_qty × avg + fill_qty × fill_price) / new_qty<br/>If closing → keep existing avg (or flip if over-closed)<br/>realized_pnl += closed × (fill_price − avg) × direction
        Pos-->>Project: new Position (frozen dataclass)
        Project-->>PM: projected Position
        PM->>StateMachine: Transition check (FLAT→OPEN / OPEN→CLOSED / etc.)
        alt Illegal transition
            StateMachine-->>PM: raise IllegalTransitionError
        else Valid transition
            StateMachine-->>PM: transition_to(new_state)
        end
        PM->>PM: Store updated position
        Note over PM: Collect events under lock,<br/>publish OUTSIDE lock
    end
    PM-->>EventBus: POSITION_UPDATED event (always)
    alt Was flat, now open
        PM-->>EventBus: POSITION_OPENED event
    end
    alt Was open, now flat
        PM-->>EventBus: POSITION_CLOSED event
    end
    PM->>Ctx: ctx.apply_trade(trade) (TOS-P5-022 mirror)
    Ctx->>Ctx: Position.with_fill(signed, price)
    Note over Ctx: PortfolioContext keeps a typed<br/>shadow of portfolio state
    PM->>Risk: (via POSITION_UPDATED subscriber)
    Risk->>Risk: update_daily_pnl(total_realized + unrealized)
```

---

## 10. Strategy Pipeline Flow

Traces from candidate generation through feature fetching (LRU-cached),
strategy evaluation, kill-switch gating, and intent building. Kill-switch
checks appear at both the `StrategyPipeline` level (via `PlanContext`) and
the `TradingOrchestrator` execution gate.

```mermaid
sequenceDiagram
    autonumber
    participant Scanner as Scanner/Ranker
    participant EventBus as EventBus
    participant Orch as TradingOrchestrator
    participant Fetcher as PipelineFeatureFetcher
    participant LRU as LRU Cache (OrderedDict)
    participant MarketData as MarketDataPort
    participant FP as FeaturePipeline
    participant Eval as StrategyEvaluator
    participant SP as StrategyPipeline
    participant Strategy as MomentumStrategy / BreakoutStrategy
    participant KillSwitch as RiskManager.kill_switch
    participant Planner as build_execution_plan()
    participant OMS as OMS

    Scanner->>EventBus: CANDIDATE_GENERATED {symbol, score}
    EventBus->>Orch: on_candidate(event)

    Note over Orch: 1. Extract candidate + correlation_id
    Orch->>Orch: Create CandidateDTO

    Note over Orch: 2. Fetch features (with optional timeout)
    Orch->>Fetcher: fetch(symbol, exchange="NSE")
    Fetcher->>LRU: Lookup cache_key = "SYMBOL:NSE"
    alt Cache hit
        LRU-->>Fetcher: cached FeatureSet
    else Cache miss
        Fetcher->>MarketData: history(symbol, start, end, interval="1m")
        MarketData-->>Fetcher: HistoricalSeries
        Fetcher->>FP: run(df.tail(lookback_bars))
        FP-->>Fetcher: features DataFrame
        Fetcher->>Fetcher: _df_to_feature_set(df)
        Fetcher->>LRU: store (evict LRU if > 256)
        LRU-->>Fetcher: ok
    end
    Fetcher-->>Orch: FeatureSet

    Note over Orch: 3. Evaluate through strategy pipeline
    Orch->>Eval: evaluate_single(candidate, features)
    Eval->>SP: evaluate_single(candidate, features)
    loop For each registered Strategy
        SP->>Strategy: evaluate(candidate, features)
        Strategy->>Strategy: Read RSI, ROC, ATR, volume, swing levels
        Strategy-->>SP: Signal (BUY/SELL/HOLD + confidence + entry/stop/target)
    end
    SP-->>Eval: list[Signal]
    Eval-->>Orch: list[SignalDTO]

    Note over Orch: 4. Execute actionable signals
    loop For each Signal
        Orch->>Orch: Check signal.is_actionable
        Orch->>Orch: Check confidence >= min_confidence
        Orch->>KillSwitch: _is_kill_switch_active()
        alt Kill switch active
            KillSwitch-->>Orch: true → reject signal
        else Kill switch off
            KillSwitch-->>Orch: false
            opt Dry run mode
                Note over Orch: Log "would execute" → skip OMS
            end
            Orch->>Planner: build_execution_plan(signal, PlanContext)
            Note over Planner: PlanContext.kill_switch_active<br/>checked again here
            Planner-->>Orch: ExecutionPlan (legs, sizing, slicing)
            Orch->>Planner: plan_to_intents(plan)
            Planner-->>Orch: list[OrderIntent]
            loop For each intent (leg)
                Orch->>OMS: _intent_to_command() → _place_order()
                OMS-->>Orch: OrderResult
            end
            Orch-->>EventBus: SIGNAL_EXECUTED / RISK_APPROVED / RISK_REJECTED
        end
    end
```

---

## 11. Replay Flow

Traces the bar-by-bar loop in `ReplayEngine`, including warmup gating, the
circular-buffer window, feature computation, strategy evaluation, and the
two fill paths: OMS-integrated (`_process_signal_via_oms`) vs simulated
(`_process_signal_simulated`). Shows the NEXT_OPEN fill model delay.

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller
    participant RE as ReplayEngine
    participant Session as ReplaySession
    participant CircularBuf as Circular Buffer (numpy)
    participant FP as FeaturePipeline
    participant SP as StrategyPipeline
    participant FillModel as Fill Model
    participant OMS as OmsBacktestAdapter
    participant Sim as Direct Simulation
    participant PnL as PnL / Equity

    Caller->>RE: run(data, symbol)
    RE->>RE: Detect ts_col, sort by timestamp
    alt Multi-symbol data
        RE->>RE: _run_multi_symbol()
    else Single symbol
        RE->>RE: _run_single(df, symbol, ts_col)
    end
    RE->>Session: Initialize ReplaySession(capital=config.initial_capital)
    RE->>Session: equity_curve.append((ts, initial_capital))

    loop For each bar (idx 0..N)
        RE->>Session: Publish scheduled events (P0-1 determinism)
        RE->>RE: Process pending_signals with bar.open (NEXT_OPEN model)

        RE->>CircularBuf: Write bar OHLCV at _head pointer (O(1))
        RE->>CircularBuf: Advance _head = (_head + 1) % window_size
        RE->>Session: bar_count += 1

        alt Warmup phase (bar_count < warmup_bars)
            RE->>RE: continue (skip strategy)
        else Warmup complete
            RE->>CircularBuf: Build window DataFrame (chronological reorder)
            CircularBuf-->>RE: window_df
            RE->>FP: run(window_df)
            FP-->>RE: features DataFrame

            RE->>RE: Create Candidate(symbol, score=50)

            alt Stop-loss / Target hit check
                RE->>RE: _close_position_at_price() via OMS or simulated
                RE->>PnL: Record trade + update equity
            else No stop/target hit
                RE->>SP: evaluate_single(candidate, features)
                SP-->>RE: list[Signal]

                loop For each Signal
                    RE->>RE: Record signal in session
                    alt Fill model: NEXT_OPEN
                        RE->>RE: Append to pending_signals (deferred to next bar)
                    else Fill model: CURRENT_CLOSE
                        alt OMS adapter available (PARITY mode)
                            RE->>OMS: open_long / close_long
                            OMS-->>RE: order_id
                            RE->>RE: _sync_session_from_tracker()
                        else No OMS (PURE_SIM mode)
                            RE->>Sim: Direct fill simulation
                            Sim->>Sim: Apply slippage, commission
                            Sim->>Sim: Deduct/add capital
                            Sim->>Sim: Record SimulatedTrade
                        end
                    end
                end
            end
            RE->>Session: mark_symbol(bar.close)
            RE->>PnL: equity_curve.append((bar_ts, current_equity))
        end
    end

    RE->>RE: Close any remaining open position ("End of replay")
    RE->>RE: Process leftover pending_signals
    RE-->>Caller: ReplayResult(session, bars_processed, signals_generated)
```

---

## 12. Backtest Flow

Traces `BacktestEngine` orchestration wrapping `ReplayEngine` with rich
performance analytics via `StatisticsEngine`. Shows the `ResearchMode`
distinction (`PURE_SIM` vs `PARITY`) and how it configures the underlying
replay engine.

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller
    participant BE as BacktestEngine
    participant Mode as ResearchMode
    participant RE as ReplayEngine
    participant FP as FeaturePipeline
    participant SP as StrategyPipeline
    participant OMS as OmsBacktestAdapter (optional)
    participant Stats as StatisticsEngine
    participant Result as BacktestResult

    Caller->>BE: BacktestEngine(pipeline, strategy, config, mode)

    alt mode == PURE_SIM
        Mode-->>BE: allow_sim = True
        Note over BE: OMS adapters are optional.<br/>Not live-parity (ENG-012).<br/>Signals simulate fills directly.
    else mode == PARITY
        Mode-->>BE: Require trading_context or oms_adapter
        alt Neither provided
            Mode-->>BE: ValueError raised
        else Provided
            Mode-->>BE: allow_sim = False
            Note over BE: Replay routes through OMS risk gates,<br/>idempotency ledger, and event bus.
        end
    end

    BE->>RE: ReplayEngine(pipeline, strategy, config,<br/>oms_adapter, allow_simulate_without_oms)

    Caller->>BE: run(data, symbol, benchmark)

    BE->>RE: run(data, symbol)
    Note over RE: Bar-by-bar loop (see Flow #11)<br/>Circular buffer → features → strategy → fills
    RE-->>BE: ReplayResult(session, trades, equity_curve)

    BE->>Stats: StatisticsEngine.compute(<br/>equity_curve, trades,<br/>initial, final,<br/>annualization_factor,<br/>risk_free_rate, benchmark)
    Stats->>Stats: total_return, CAGR, volatility
    Stats->>Stats: sharpe_ratio, sortino_ratio, calmar_ratio
    Stats->>Stats: max_drawdown, max_drawdown_duration
    Stats->>Stats: profit_factor, expected_value, payoff_ratio
    Stats->>Stats: win/loss streaks, avg_holding_bars
    opt benchmark provided
        Stats->>Stats: alpha, beta, tracking_error, information_ratio
    end
    Stats-->>BE: computed dict

    BE->>BE: Map → PerformanceMetrics
    BE->>BE: _trade_analysis_from_stats(stats.trade_analysis)
    BE-->>Result: BacktestResult(replay, metrics,<br/>benchmark_data, equity_curve)
    Result-->>Caller: BacktestResult
```

---

## 13. WebSocket Reconnection Flow

Traces the `ReconnectController` reconnect loop from transport-loss detection
through exponential backoff, reconnection attempts, and cross-broker failover.
Shows backoff parameters and the heartbeat staleness monitor.

```mermaid
sequenceDiagram
    autonumber
    participant Orchestrator as StreamOrchestrator
    participant RC as ReconnectController
    participant Session as StreamSession
    participant Handle as BrokerStreamHandle
    participant GW as BrokerGateway
    participant Router as BrokerRouter
    participant Registry as BrokerRegistry
    participant HB as Heartbeat Loop

    Note over RC: Constants:<br/>BASE_DELAY = 1.0s<br/>MAX_DELAY = 60.0s<br/>MAX_ATTEMPTS = 5<br/>HEARTBEAT_INTERVAL = 5.0s

    Orchestrator->>RC: reconnect_loop(session_id, original_request)

    loop While running (every 1.0s poll)
        RC->>Session: Get session by session_id
        RC->>Handle: is_connected()
        alt Transport healthy
            Handle-->>RC: true → continue monitoring
        else Transport lost
            Handle-->>RC: false
            RC->>Session: update_transport(RECONNECTING)
            RC->>Session: increment_reconnect()
            RC->>RC: sleep(delay) [exponential backoff]

            Note over RC: delay = min(delay × 2, 60.0s)

            alt Reconnect attempts >= MAX_ATTEMPTS (5) AND failover allowed
                RC->>Router: _try_failover(session_id, session, original_request)
                Router->>Router: route(RoutingRequest)
                alt Routing failed
                    Router-->>RC: exception → continue same broker
                else Fallback brokers available
                    loop For each fallback broker (skip current)
                        RC->>Registry: get_gateway(fallback_broker)
                        RC->>GW: open_market_stream / open_order_stream
                        alt Success
                            GW-->>RC: new handle
                            RC->>Session: update_transport(CONNECTED)
                            RC->>Session: reconnect_generation = 0
                            RC->>RC: object.__setattr__(session, broker_id, fallback)
                            RC-->>RC: return True (failover succeeded)
                        else Broker failed
                            GW-->>RC: exception → try next broker
                        end
                    end
                    RC-->>RC: return False (no brokers left)
                end
            else Re-attempt on same broker
                RC->>Registry: get_gateway(session.broker_id)
                RC->>GW: open_market_stream / open_order_stream
                alt Reconnection success
                    GW-->>RC: new handle
                    RC->>Session: update_transport(CONNECTED)
                    RC->>Session: update_subscription(ACKNOWLEDGED)
                    RC->>Session: update_freshness(UNKNOWN)
                    RC->>RC: delay = BASE_DELAY (reset)
                else Reconnection failure
                    GW-->>RC: exception
                    Note over RC: Log failure, next iteration<br/>with doubled delay
                end
            end
        end
    end

    Note over HB: Separate async task
    loop Every HEARTBEAT_INTERVAL (5.0s)
        HB->>HB: For each session
        HB->>HB: Check (now - last_valid_tick_at)
        alt Elapsed > stale_seconds_threshold
            HB->>Session: update_freshness(STALE)
            HB-->>Orchestrator: notify_health_change(session_id, health)
        end
    end
```

---

## 14. Graceful Shutdown Flow

Traces the full shutdown sequence from OS signal receipt through
`TradingContext._execute_shutdown_sequence`, then `LifecycleManager.stop_all()`
with its reverse-order, timeout-enforced daemon-thread pattern.

```mermaid
sequenceDiagram
    autonumber
    participant OS as OS / Docker
    participant Handler as Signal Handler
    participant TC as TradingContext
    participant Risk as RiskManager
    participant OMS as OrderManager
    participant Broker as BrokerGateway
    participant EL as EventLog
    participant EB as EventBus
    participant LM as LifecycleManager
    participant SvcA as Service A (earliest)
    participant SvcB as Service B (latest)

    OS->>Handler: SIGTERM / SIGINT
    Handler->>TC: _sync_shutdown()
    Note over TC: Acquire _shutdown_lock<br/>Idempotency: skip if already in progress
    TC->>TC: _execute_shutdown_sequence()

    Note over TC: Step 1: Halt new order placement
    TC->>Risk: set_kill_switch(True)
    Risk-->>TC: Kill switch activated

    Note over TC: Step 2: Cancel all open orders
    TC->>OMS: Get OPEN orders
    OMS-->>TC: list[Order]
    loop For each open order
        TC->>Broker: cancel_order(order_id)
        alt Cancel succeeded
            Broker-->>TC: success → cancelled += 1
        else Cancel failed
            Broker-->>TC: error → failed += 1
        end
        TC->>OMS: cancel_order(order_id) [local status]
    end

    Note over TC: Step 3: Flush event log to disk
    TC->>EL: flush()
    EL-->>TC: flushed
    TC->>EL: close()
    EL-->>TC: closed

    Note over TC: Step 4: Emit SYSTEM_SHUTDOWN event
    TC->>EB: publish(SYSTEM_SHUTDOWN)
    EB-->>TC: ok

    TC-->>Handler: shutdown result dict

    Note over Handler: Restore original signal handler,<br/>re-raise signal for default behavior

    Note over LM: LifecycleManager.stop_all()<br/>Called via ManagedService.stop() on TC
    TC->>LM: stop_all()
    LM->>LM: Iterate services in REVERSE registration order

    loop For each service (reverse order: B then A)
        LM->>LM: _stop_one(service_name)
        Note over LM: Create daemon thread running service.stop()
        LM->>SvcB: Thread(target=service.stop) → start()
        LM->>LM: thread.join(timeout=default_stop_timeout)
        alt Thread joined within timeout
            LM->>LM: started.discard(name)
            Note over LM: Service stopped cleanly
        else Thread still alive (timeout exceeded)
            Note over LM: ERROR: service did not stop within Ns<br/>Abandon daemon thread<br/>Mark FAILED in health snapshot
            LM->>LM: _last_health[name] = FAILED
            Note over LM: Daemon thread abandoned —<br/>process exit will reap it
        end
    end
```

---

## 15. Recovery Flow

Traces the process-restart recovery path: `ParityGate` verification of
determinism guarantees, state reconstruction from the persisted event log,
and event replay to reach a consistent ready state.

```mermaid
sequenceDiagram
    autonumber
    participant Process as New Process
    participant Config as Config / Env
    participant Gate as ParityGate
    participant Pytest as pytest (subprocess)
    participant ReplayTest as test_event_replay_determinism.py
    participant QuantVerify as baseline_quant_parity.py
    participant ShadowTest as test_shadow_parity_gate.py
    participant EL as Event Log (persisted)
    participant Replay as Event Replay
    participant State as State Reconstruction
    participant Runtime as Runtime (ready)

    Process->>Config: Read SKIP_PARITY_GATE env var
    alt SKIP_PARITY_GATE=1 (local dev / tests)
        Config-->>Gate: skip = true
        Gate-->>Process: Skip parity gate (debug mode)
    else PYTEST_CURRENT_TEST set
        Gate-->>Process: Skip (already in test runner)
    else Production mode
        Gate->>Gate: failures = []

        Note over Gate: Verifier 1: Event Replay Determinism
        Gate->>Pytest: subprocess.run(pytest test_event_replay_determinism.py)
        Pytest->>ReplayTest: Execute determinism checks
        ReplayTest->>ReplayTest: Replay event sequence twice
        ReplayTest->>ReplayTest: Compare final state hashes
        alt Test passed
            ReplayTest-->>Pytest: returncode=0
        else Test failed
            ReplayTest-->>Pytest: returncode!=0
            Gate->>Gate: failures.append("event_replay_verifier")
        end

        Note over Gate: Verifier 2: Quant Parity Baseline
        Gate->>QuantVerify: subprocess.run(baseline_quant_parity.py --mode verify)
        QuantVerify->>QuantVerify: Re-compute baseline metrics
        QuantVerify->>QuantVerify: Compare against stored golden values
        alt Test passed
            QuantVerify-->>Gate: returncode=0
        else Test failed
            QuantVerify-->>Gate: returncode!=0
            Gate->>Gate: failures.append("quant_parity_baseline")
        end

        Note over Gate: Verifier 3: Shadow Parity Gate
        Gate->>Pytest: subprocess.run(pytest test_shadow_parity_gate.py)
        Pytest->>ShadowTest: Execute shadow parity checks
        ShadowTest->>ShadowTest: Verify shadow mode matches authority
        alt Test passed
            ShadowTest-->>Pytest: returncode=0
        else Test failed
            ShadowTest-->>Pytest: returncode!=0
            Gate->>Gate: failures.append("shadow_parity_gate")
        end

        alt Any verifier failed
            Gate-->>Process: raise RuntimeError("Runtime parity gate failed")
            Note over Process: Process refuses to start —<br/>determinism cannot be guaranteed
        else All verifiers passed
            Gate-->>Process: Log "Runtime parity gate passed"
        end
    end

    Note over Process: State Reconstruction from Event Log
    Process->>EL: Open persisted event log
    EL-->>Process: Event stream (ordered by sequence number)
    Process->>Replay: Replay events from log
    loop For each event in log
        Replay->>State: Apply event to in-memory state
        Note over State: Positions, orders, balances<br/>reconstructed deterministically
    end
    Replay->>Replay: Verify replayed state hash matches last checkpoint
    alt Hash mismatch
        Replay-->>Process: raise DeterminismError
        Note over Process: Abort — state is inconsistent
    else Hash matches
        Replay-->>Process: State reconstructed successfully
    end
    Process->>Runtime: Emit READY event
    Note over Runtime: System accepts new events<br/>and resumes live trading
```
