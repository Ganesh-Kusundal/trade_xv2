# Prioritized Architecture Audit — Trade_XV2

> Code-derived findings only (graphify + source). Companion to [`CURRENT-STATE.md`](CURRENT-STATE.md).
> Date: 2026-07-13. Severity ranked for a **real-money** system.

---

## Scoring

| Priority | Meaning |
|---|---|
| **P0** | Correctness / safety: can lose money, crash core path, or silently defeat a safety gate |
| **P1** | Layer-contract false-green or silent data-key mismatch |
| **P2** | Structural / SOLID / duplication that forces shotgun surgery |
| **P3** | Latent real-time hazards and typing traps |

For each finding: **what can go wrong silently**, **what breaks under real-time**, **unsafe assumptions**, **implicit vs explicit**.

---

## P0 — Money / crash / safety bypass

### F3 — Parity gate defeated by code default

| | |
|---|---|
| **Where** | `src/interface/ui/services/compose.py:22` (`skip_parity_gate: bool = True`); also `interface/ui/main.py:150`, `tradex/session.py:277` |
| **Evidence** | `TradingRuntimeFactory` only runs `assert_runtime_parity_or_raise` when `not self._skip_parity_gate` (`trading_runtime_factory.py:91`). Prod config inspects env `SKIP_PARITY_GATE`, not the hardcoded CLI default. |
| **Silent** | Live CLI boots without replay/quant/shadow parity verification; operators believe the gate ran. |
| **Unsafe assumption** | “Production config validation implies parity ran.” |
| **Implicit** | Skip is a function default, not an explicit operator decision. |

### F5 — Daily-loss limit is absolute MTM, not session realized loss

| | |
|---|---|
| **Where** | `TradingContext._feed_daily_pnl` (`application/oms/context.py:379-403`); `DailyPnlTracker.update`; `RiskManager` daily-loss check |
| **Evidence** | Feeds `Σ(realized + unrealized)` absolute book PnL every position event. Docstring admits absolute total; check treats it as daily loss. |
| **Silent** | Open underwater position can halt **all** new orders for the day; green open position can **mask** realized intraday loss. |
| **Real-time** | MTM noise trips or relaxes the gate incorrectly throughout the session. |
| **Unsafe assumption** | “Daily PnL tracker measures intraday realized loss.” |

### F4 — Reconciliation detects drift; does not heal OMS

| | |
|---|---|
| **Where** | `ReconciliationService._run_once` → `ExecutionEngine.apply_mass_status` (`execution_engine.py:49-89`); Upstox/Dhan `auto_repair` defaults False |
| **Evidence** | `apply_mass_status` builds `drift_items` and **returns them without writing** order book or positions. Docstring still claims “healing drift”. Broker adapters heal only when `auto_repair=True` and only some HIGH severities. |
| **Silent** | Missed WS fills → permanent local/broker divergence; `RECONCILIATION_DRIFT` looks like correction. |
| **Unsafe assumption** | “Reconciliation reconciles.” |
| **Implicit** | Healing named in docs/method; behavior is report-only. |

### F2e — ReplayEngine crashes on pending end-of-run signal

| | |
|---|---|
| **Where** | `src/analytics/replay/engine.py:512` and `:635` — `self._publish_signal(sig)` |
| **Evidence** | Module imports helper as `_publish_sig`; no `_publish_signal` method on the class. Default fill model is `NEXT_OPEN` → pending signals common on final bar. |
| **Real-time / batch** | Guaranteed `AttributeError` after trades may already be recorded — aborted run, partial results. |

### F2a — Paper double-applies slippage (zero-parity)

| | |
|---|---|
| **Where** | `analytics/paper/signal_processor.py:82,128` (`_apply_slippage` locally); `application/execution/oms_backtest_adapter.py` (`apply_slippage` again) |
| **Evidence** | Replay OMS path passes un-slipped base price into adapter; paper slips then calls same adapter. |
| **Silent** | Paper P&L ≈ 2× slippage vs replay on identical data. |

### F2b — Paper has no `fill_model`

| | |
|---|---|
| **Where** | `analytics/paper/models.py` (`PaperConfig` — no `fill_model`); engine always fills at `bar.close` |
| **Evidence** | `ReplayConfig.fill_model` defaults `NEXT_OPEN` (`replay/models.py`). |
| **Silent** | Same strategy + data ≠ same fills across modes. |

### F2c / F2d — Commission and session/OMS capital desync

| | |
|---|---|
| **Where** | Paper open: `commission_flat` only (`signal_processor`); closer uses `max(pct, flat)`; replay uses `domain.trading_costs.compute_commission`. Replay session records un-slipped price while OMS records slipped (`replay/signal_processor` vs adapter). |
| **Silent** | Equity from session ≠ OMS book; commission differs paper vs replay. |

### F2f — Default backtest skips OMS

| | |
|---|---|
| **Where** | `BacktestEngine` defaults `ResearchMode.PURE_SIM` (`analytics/backtest/engine.py`) → `oms_adapter=None` → `_process_simulated` |
| **Silent** | “Backtest” has no risk/idempotency/OMS events; parity is opt-in (`ResearchMode.PARITY`). |
| **Unsafe assumption** | “Any backtest equals live path.” |

### F6 — Order idempotency not durable across restart

| | |
|---|---|
| **Where** | `IdempotencyGuard` + `MemoryIdempotencyCache` (`application/oms/idempotency_guard.py:18-19`); `_orders_by_correlation` in-memory |
| **Evidence** | Trade-level durable store exists; order-level correlation dedupe does not. |
| **Silent / real-money** | Crash during `submit_fn` after broker accept → restart → same correlation → **second live order**. |
| **Unsafe assumption** | “Correlation_id makes retries safe forever.” |

---

## P1 — Layer contract / key consistency

### F1 — `application` → `infrastructure` (false-green)

Direct imports (non-exhaustive of comments):

| File | Import |
|---|---|
| `application/oms/idempotency_guard.py:18-19` | `MemoryIdempotencyCache`, `IdempotencyService` |
| `application/services/historical_data.py` | `infrastructure.historical_data` |
| `application/services/download_engine.py` | parquet IO / gateway types |
| `application/data/historical_coordinator.py` | `infrastructure.observability.audit` |
| `application/streaming/orchestrator.py` | audit emits |
| `application/scheduling/quota_scheduler.py` | audit emits |
| `application/composer/router.py` | audit emits |
| `application/services/production_readiness.py` | `ssl_hardening` |

`domain.ports.observability` and idempotency backends exist; application bypasses them. Import-linter appearing green is misleading.

### F9 — API → UI upward imports

| File | Import |
|---|---|
| `interface/api/routers/live/portfolio.py:26-27` | `interface.ui.services.active_session`, `market_access` |
| `interface/api/bootstrap.py:31` | `interface.ui.services.compose.build_for_api` |

API depends on UI; UI is no longer a leaf.

### F8 — `normalize_symbol` split-brain

| Impl | Behavior |
|---|---|
| `domain/symbols.py:19` | `strip().upper()` — **keeps** `RELIANCE-EQ` |
| `datalake/core/symbols.py:29` | strip/upper **then** strip `-EQ`/`-BE`/… |

~58 call sites. Reconciliation / position keys can miss **silently**.

### F7 — Multiple composition roots / OMS / command mapping

- OMS: `create_trading_context` vs `build_oms_service`
- Roots: `compose`/`TradingRuntimeFactory` vs `tradex.open_session`
- `PlaceOrderCommand` closures duplicated (≥3)

Shotgun surgery for any new order field.

---

## P2 — Structural / SOLID

### Brokers

- Upstox vs Dhan: parallel wire surfaces; little shared core beyond `brokers/common/*` and `brokers/services/core.py` (SDK/CLI/MCP facade is healthy).
- `authenticate()`: Upstox reconnects; Dhan status no-op — **LSP** on `BrokerAdapter`.
- God classes: `UpstoxBroker` (~468 LOC), `DhanConnection` (~590 LOC).
- Dead `src/brokers/next/` (empty tree); `BrokerGateway` alias on Dhan wire invites wrong imports.
- Certification: golden/mapping/market_hours real; token-refresh / reconnect / recovery / orders largely `warn_only` / stubs — money paths not fail-certifying.

### Runtime / application gods

- `BrokerService` (~480 LOC): gateway + OMS + WS + recon + lifecycle; runtime reaches private UI attrs (`_event_bus`, etc.) — DIP.
- `TradingContext` (~577 LOC): wiring + PnL feed + shutdown + replay.
- `OrderPlacer.order_command_fn` escape hatch (P0-adjacent if miswired).

### Analytics duplication

- Four Trade/Position shapes (domain / replay / paper).
- Windowing in three places (inline numpy in `ReplayEngine`, `window.py`, paper `BarWindowManager`).
- Two ATR styles (SMA in features vs Wilder for HalfTrend) — strategies see different ATR.
- Indicator shims in `analytics/indicators/*` re-export domain.

### Domain leftovers

- Two `BrokerId` enums (`enums.py` vs `ports/broker_id.py`).
- Triplicated `_as_money` / `_as_quantity` on entities.
- `StatusMapperRegistry` import-time population → import-order coupling.

### What is healthy (do not “fix”)

- Rate limiter: single module under infrastructure.
- EventBus: port in domain; one prod impl; no FakeEventBus on production paths.

---

## P3 — Latent real-time / typing

| ID | Finding | Location / note |
|---|---|---|
| R-async | `asyncio.run(build_infrastructure)` inside factory | `trading_runtime_factory` — fails under running loop; orphans stream tasks when loop closes |
| R2 | Risk-pending notional no TTL; release only on terminal upsert | `RiskManager.reserve_pending` / `MarginChecker` — stuck OPEN orders inflate exposure forever |
| R3 | Transient double-count fill vs pending | Gross exposure overcount → spurious rejects |
| R4 | Burst same-symbol concentration undercount | Positions lag `TRADE_APPLIED`; pending not fully summed for concentration |
| T1 | `MarketDataGateway` alias collision | `BrokerTransport` vs `BrokerAdapter` — `Runtime.gateway` effectively `Any` |
| T2 | `Money.__eq__` coerces str/int | Masks type bugs |
| G1 | Process globals | `set_live_actionable_gate`, `require_execution_ledger`, shared quota — last writer wins with multiple services |

---

## Invariant checklist (audit snapshot)

| Invariant | Status |
|---|---|
| Domain imports no outer layer | PASS |
| Brokers import no application/interface | PASS |
| Application imports no infrastructure | FAIL (F1) |
| Zero-parity P&L | FAIL (F2*) |
| Parity gate before live boot | FAIL (F3) |
| Reconciliation heals | FAIL (F4) |
| Daily loss = realized session | FAIL (F5) |
| Durable order idempotency | FAIL (F6) |
| One composition root / OMS | FAIL (F7) |
| One normalize_symbol | FAIL (F8) |
| API ↛ UI | FAIL (F9) |

---

## Answers-only summary (principal reviewer lens)

**What can go wrong silently?**  
Parity skipped; paper P&L ≠ replay; recon “heals” nothing; daily-loss mis-calibrated; symbol keys disagree; restart double-submit.

**What breaks under real-time?**  
Missed WS + no heal; risk-pending leak; burst concentration slip; `asyncio.run` under API loop; orchestrator/multi-broker silently `None`.

**Unsafe assumptions?**  
“Reconciliation reconciles”; “daily PnL is daily realized”; “correlation_id is durable”; “backtest implies OMS”; “authenticate() reconnects on every broker.”

**Where is behavior implicit?**  
Skip-parity defaults; heal-named no-op; stub-before-submit idempotency ordering; paper vs replay fill semantics; import-time status mappers.

---

## Cross-Reference

- Current map/flows: [`CURRENT-STATE.md`](CURRENT-STATE.md)
- Target + migration: [`TARGET-STATE.md`](TARGET-STATE.md)
