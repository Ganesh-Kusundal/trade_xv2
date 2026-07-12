# 07 — Risk & Safety

Reference: Nautilus `RiskEngine` (`nautilus_trader/risk/engine.pyx`), TradingState ACTIVE/REDUCING/HALTED, Throttler, live denial policy.

TradeXV2 current core: `application/oms/_internal/risk_manager.py`.

---

## 1. TradingState (target, from Nautilus)

| State | Allowed |
|---|---|
| **ACTIVE** | New risk, modifies, cancels |
| **REDUCING** | Only orders/modifies that reduce exposure; cancels OK |
| **HALTED** | Cancels only (optional policy); no new risk. TradeXV2 kill-switch today is stricter: **freeze_all** (blocks exit_all too) |

Document desk policy explicitly:
- Current desk: `KILL_SWITCH_MODE = freeze_all` (compromised process must not emergency-exit).
- Operators clear kill-switch, then flatten.

---

## 2. Pre-trade gate order (`check_order`)

Fail-closed, under lock:

1. Kill-switch active → deny  
2. Domain KillSwitch policy (optional) → deny  
3. TradingState HALTED / REDUCING violation → deny  
4. Loss circuit breaker (rolling window) → deny  
5. Submit/modify Throttler → deny or queue-drop  
6. Tick alignment (instrument resolve) → **deny on provider fault** (I9; as-built warns — gap)  
7. Capital > 0  
8. Margin (F&O segments)  
9. Effective notional (MARKET needs LTP/ref)  
10. Per-symbol concentration vs `max_position_pct` (includes pending reservations)  
11. Gross exposure vs `max_gross_exposure_pct`  
12. Daily loss vs `max_daily_loss_pct`  
13. On pass → `reserve_pending(correlation_id, notional)`

---

## 3. Post-trade monitoring

| Signal | Action |
|---|---|
| Daily PnL update | `update_daily_pnl`; may emit `RISK_LIMIT_BREACHED` before hard deny |
| Loss circuit trip | Open breaker; deny new risk |
| Drawdown limit | `DRAWDOWN_LIMIT_HIT`; optionally → REDUCING/HALTED |
| Broker disconnect | degrade Data/Execution; do not silently trade stale marks |

### Daily PnL reset
- Scheduler at 00:00 IST remains.  
- **Required self-heal:** if `Clock.now() - last_reset_at >= session policy`, reset inside `check_order` before evaluating daily loss (as-built gap).

---

## 4. Throttling (Nautilus Throttler)

Configure e.g. `max_order_submit_rate`, `max_order_modify_rate`.  
On drop: local deny / OrderDenied — never burst the venue.

---

## 5. Expected Behavior Contract — RiskEngine

| | |
|---|---|
| **Inputs** | Order snapshot + Cache positions + capital + Clock |
| **Outputs** | RiskResult; optional RISK_* events; pending reservation |
| **Timing** | Pure function of inputs under lock; no network except margin/instrument ports with hard timeout → deny |
| **State** | kill-switch, daily_pnl, loss_cb, TradingState, throttler counters |
| **Failure modes** | Any dependency fault → deny (I9). Never “allow because check skipped” |

---

## 6. As-built gaps (risk)

| Gap | Fix |
|---|---|
| Instrument lookup `except` → warning | Hard deny |
| No TradingState REDUCING/HALTED | Add |
| No submit Throttler | Add at ExecutionEngine boundary |
| Daily reset depends only on external scheduler | Self-heal in check_order |
| G7 getattr kill-switch | Largely fixed via RiskManagerPort injection — keep arch guard |
