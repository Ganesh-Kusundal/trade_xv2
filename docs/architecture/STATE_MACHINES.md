# STATE_MACHINES.md — Finite State Machines

> Canonical state-transition tables for the system. Each table below is pulled directly from
> the source module that owns it — this file is a reading index, not a second source of
> truth. If a table here disagrees with the linked source file, the source file wins; fix
> this doc.

---

## 1. Order FSM

Source: `src/domain/entities/order_lifecycle.py` (`ORDER_STATUS_TRANSITIONS`).

| From | Allowed → | 
|---|---|
| `OPEN` | `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `PARTIALLY_CANCELLED`, `REJECTED`, `EXPIRED` |
| `PARTIALLY_FILLED` | `FILLED`, `CANCELLED`, `PARTIALLY_CANCELLED`, `REJECTED` |
| `FILLED` | *(terminal — no transitions)* |
| `CANCELLED` | *(terminal)* |
| `PARTIALLY_CANCELLED` | *(terminal)* |
| `REJECTED` | *(terminal)* |
| `EXPIRED` | *(terminal)* |
| `UNKNOWN` | `OPEN`, `REJECTED`, `CANCELLED` |

Illegal transitions (e.g. `FILLED` → `OPEN`) must raise, not silently apply — this is
invariant I7. Enforcement point: any code that mutates order status must route through this
table, not a direct field assignment (`Order.with_status` bypassing the table is a tracked
as-built gap — see `docs/architecture/backlog.md`).

## 2. Position FSM

Source: `src/domain/entities/position.py` (`POSITION_STATE_TRANSITIONS`).

| From | Allowed → |
|---|---|
| `FLAT` | `OPEN`, `REVERSED` |
| `OPEN` | `OPEN`, `REDUCING`, `CLOSED`, `REVERSED` |
| `REDUCING` | `FLAT`, `OPEN`, `REVERSED`, `CLOSED` |

Position transitions are driven by `PositionManager.apply_trade` off the `TRADE_APPLIED` event
(see `FLOWS.md` §7) — never mutated directly by broker-dict upserts (a tracked gap; see
`docs/architecture/e2e-spec/09-reconciliation-and-cache.md` §6).

## 3. TradingState FSM (risk gate)

Source: `src/application/oms/_internal/trading_state.py` (`TradingStateEnum`, landed via
commit `7991a70e`, modeled after Nautilus `RiskEngine` trading state).

| State | Effect |
|---|---|
| `ACTIVE` | Normal trading — all orders allowed. |
| `REDUCING` | Only risk-reducing orders allowed (e.g. sell-to-close on a long, buy-to-cover on a short, quantity capped at the current position). |
| `HALTED` | No new orders allowed. |

`TradingState.allows_new_order(side, current_qty, new_qty)` is the single gate function; it
starts at `ACTIVE` on construction.

## 4. Component FSM (engines/services)

Source: Nautilus-referenced pattern, `docs/architecture/e2e-spec/02-kernel-and-components.md`.

```
PRE_INITIALIZED → READY → STARTING → RUNNING → STOPPING → STOPPED
RUNNING → DEGRADING → DEGRADED → STOPPING | FAULTING
RUNNING → FAULTING → FAULTED → DISPOSING → DISPOSED
STOPPED → RESETTING → READY
```

Transitional states (`STARTING`, `STOPPING`, `RESETTING`, `DISPOSING`, `DEGRADING`,
`FAULTING`) should be brief — a component should not remain in one for an extended period.
`DEGRADED` is used, in particular, while reconciliation (§9 in `FLOWS.md`) is in progress
after a reconnect: new risk decisions wait for `RUNNING` to resume.

## 5. Environment (frozen at boot, not a runtime FSM)

Source: `docs/architecture/e2e-spec/08-time-parity-and-environments.md` — see `FLOWS.md` §11
for the full table. `Environment` (`BACKTEST` / `SANDBOX` / `LIVE`) is set once at composition
time and does not transition during a process's lifetime — listed here only because it gates
which FSMs above are live (e.g. `TradingState` still applies in all three; `FillSource`
selection does not).
