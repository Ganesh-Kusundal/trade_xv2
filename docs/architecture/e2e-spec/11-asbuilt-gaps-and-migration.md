# 11 — As-Built Gaps & Migration Plan

This document gates implementation. It maps current code to the E2E spec and orders the work. Reference reviews:

- `docs/superpowers/reviews/PRINCIPAL-ENGINEER-REVIEW-TradeXV2-vs-nautilus.md`
- `docs/architecture/backlog.md` (G1–G8)
- Nautilus kernel/execution/risk/cache contracts (`00-nautilus-reference.md`)

---

## 1. Gap matrix (spec ID → as-built)

| Spec | As-built | Severity | Evidence |
|---|---|---|---|
| I1 Zero-Parity engine | Live inlined; replay `SimulatedOMSAdapter` | 🔴 | `execution_mode_adapter.py` docstring; dual paths |
| I2 Clock in fills | `datetime.now()` in paper/mappers | 🔴 | `paper_orders.py`, `derivatives_mapper.py`, … |
| I6 Hot-path reconcile | Detached services (G6) | 🔴 | `reconciliation_service.py`, broker reconciliation modules |
| I7 Order FSM | Table exists; `Order.with_status` bypasses | 🔴 | `order.py:112`, `order_lifecycle.py` |
| I8 Single idempotency | 4 systems | ⚠️ | brokers + oms + infrastructure |
| I9 Fail-closed risk | Instrument lookup swallowed | 🔴 | `risk_manager.py` tick check `except` |
| I10 Single bus | ~8 implementations | ⚠️ | event_bus trees |
| Daily PnL self-heal | External scheduler only | ⚠️ | `reset_daily_pnl` docs |
| TradingState + Throttler | Missing | ⚠️ | vs Nautilus RiskEngine |
| G1 broker string branch | Largely DONE | — | backlog |
| G2 shadow brokers | DONE | — | backlog |
| G3 datalake NSE/IST | Open | 🔴 | ADR-005 |
| G4 dual config | Open | ⚠️ | |
| G7 getattr kill-switch | Mostly fixed via port | — | orchestrator injection |

---

## 2. Migration phases (documentation-first → implement)

### Phase A — Close silent money bugs (no redesign yet)
| Step | Change | Acceptance |
|---|---|---|
| A1 | `Order.with_status` → StateMachine + `ORDER_STATUS_TRANSITIONS` | Illegal transitions raise; unit + one integration |
| A2 | Inject Clock into fill builders; purge `datetime.now` on listed paths | Arch grep test green |
| A3 | Instrument lookup failure → RiskResult(False) | Test: provider raise ⇒ deny |
| A4 | Daily PnL self-heal on staleness in `check_order` | Test: stale last_reset ⇒ reset then evaluate |

### Phase B — Structural Zero-Parity (Nautilus-aligned)
| Step | Change | Acceptance |
|---|---|---|
| B1 | Introduce ExecutionEngine façade; both live + sim FillSources | Single place_order entry; delete duplicate adapter path |
| B2 | Move reconcile apply into ExecutionEngine | No HIGH drift window after mass-status; delete detached healer as sole path |
| B3 | TradingCache façade over order/position dicts | Risk + strategy read Cache API |
| B4 | Collapse EventBus to one + one IdempotencyGuard | Arch tests ban second bus / second idempotency ctor in runtime |

### Phase C — Risk parity with Nautilus
| Step | Change | Acceptance |
|---|---|---|
| C1 | TradingState ACTIVE/REDUCING/HALTED | State machine tested |
| C2 | Submit/modify Throttler | Burst denied locally |
| C3 | Live parity gate non-skippable | `SKIP_PARITY_GATE` ignored when Environment.LIVE |

### Phase D — Exchange / config cleanup
| Step | Change | Acceptance |
|---|---|---|
| D1 | ExchangeAdapter + TradingCalendar plugins (G3) | Datalake raises if unset |
| D2 | Single AppConfig (G4) | One settings source |

---

## 3. Acceptance tests (must exist before claiming done)

1. **Replay determinism:** same catalog + FakeClock ⇒ identical correlation_id order stream (timestamps included).  
2. **Risk deny never hits venue:** mock FillSource; kill-switch on ⇒ zero submit calls.  
3. **Reconcile heals phantom position:** inject local-only open position; mass-status empty ⇒ Cache flat before next check_order.  
4. **Idempotent place:** double place same correlation_id ⇒ one venue submit.  
5. **Illegal order transition:** FILLED → OPEN raises.  
6. **Clock purity:** CI grep forbids `datetime.now` under `src/brokers/**/orders|paper|mappers` and domain event builders.

---

## 4. Implementation rule (from Principal review)

> If more than two local fixes are required for a flow, redesign the flow.

Phases A can ship as small PRs. Phase B is a redesign of execution/reconcile — do not “patch around” dual adapters.

---

## 5. Doc ownership

| Doc | Owner role |
|---|---|
| 00–02 | Runtime / Platform |
| 03–04 | Domain |
| 05 | Market data |
| 06–07, 09 | OMS / Risk |
| 08 | Quant / Research + Runtime |
| 10–11 | Architecture council |

Updates to this suite require the same review bar as ADRs when changing invariants I1–I10.
