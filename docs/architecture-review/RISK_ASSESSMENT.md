# Risk Assessment — TradingOS Transformation

**Deliverable 16.** Status: DESIGN ONLY. Risks are about the *transformation*, not trading
P&L (though operational trading risk is included). Each risk: description, impact, likelihood,
mitigation, owner.

## 1. Technical / Architectural
| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Hidden layer violation `brokers.common → dhan/upstox` (D1) ships to prod | Broker coupling, regressions on broker add | High (already present) | Phase A guardrails; registry/plugin (D1 fix) | Broker Platform |
| R2 | `brokers/` god-package (86k LOC) makes changes risky | Slow, wide-blast changes | Med | Phase D/G shrink + split | Broker Platform |
| R3 | Parallel domain models (`aggregates` vs `entities`) drift | Ambiguous truth, bugs | High (present) | Phase B consolidate; lint gate | Domain Eng |
| R4 | OMS→infra coupling (D4) blocks testability | Untestable OMS, hidden deps | Med | Phase F port-extract | OMS Div |
| R5 | Event ordering/replay fidelity loss | Backtest ≠ live (false confidence) | Med | Phase F Event Store + sequence; replay test | Market Data |
| R6 | Capability drift across brokers | `session.equity(...)` behaves differently | Med | BrokerCapabilities gates `.broker.<cap>` | Broker Platform |

## 2. Operational (trading)
| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R7 | Live order placed during refactor with wrong lifecycle | Real loss | Low-Med | Kill-switch; paper-first; parity gate; dry-run default | OMS Div |
| R8 | Reconciliation gap (OMS vs broker) after state-machine change | Positions/PnL wrong | Med | Reconciliation service; post-change reconciliation test | OMS Div |
| R9 | Data correctness regression in normalization | Bad signals/orders | Med | Single normalization boundary (D6); data-lake validation | Market Data |
| R10 | Clock/race issues in EventBus under load | Missed/dup events | Low-Med | Sharded locks, DLQ, priority (already built); load tests | Platform Eng |

## 3. Migration / Delivery
| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R11 | Big-bang rewrite temptation | Total breakage | Low (charter forbids) | Incremental; never rewrite; feature-flag | Chief Architect |
| R12 | Refactor regresses working features | User-facing breakage | Med | Characterization tests first; parity gate; phased merge | Integration |
| R13 | Guardrails false-green (masked violations) | Silent decay | Med (present) | Phase A honest guardrails; internal-import lint | Chief Architect |
| R14 | Scope creep beyond A–G | Never ships | Med | Phase gate; review-before-next-major (Loop step 11) | Exec Council |

## 4. Organizational
| ID | Risk | Impact | Likelihood | Mitigation | Owner |
|---|---|---|---|---|---|
| R15 | Knowledge concentration in few modules/files | Bus factor | Med | Bounded contexts; docs/ADRs; paired review | Exec Council |
| R16 | Review bottleneck (every major change waits) | Slow throughput | Med | Parallel phases at boundaries; clear validators | Architecture Board |

## 5. Overall posture
The transformation is **low catastrophic risk** because it is incremental, guardrail-gated, and
reuses existing IP. The dominant risks (R1, R3, R13) are precisely what **Phase A + B** close
first, which is why the roadmap starts there. Operational trading risks (R7–R10) are contained by
the existing parity gate, dry-run default, and reconciliation — keep them on through every phase.
