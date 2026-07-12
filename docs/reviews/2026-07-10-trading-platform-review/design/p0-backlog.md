# P0 Implementation Backlog

This backlog is ordered by safety dependency. It is not a file-by-file patch list.

## P0.1 Freeze and classify money-moving modes

**Outcome:** unattended live trading remains blocked; `PURE_SIM` and `FastBacktestEngine` are explicitly research-only.  
**Evidence:** every result identifies execution mode, data provenance, fill model, risk path, and parity status.  
**Depends on:** none.

## P0.2 Define and version the ledger contracts

**Outcome:** implement schemas for market event, signal decision, risk reservation, order intent, submission outcome, fill, transition, discrepancy, checkpoint, and readiness.  
**Evidence:** serialization round trips preserve IDs, timestamps, versions, and failure states.  
**Depends on:** P0.1.

## P0.3 Establish durable intent-before-submit

**Outcome:** an order cannot reach a broker before durable intent and reservation.  
**Evidence:** crash between persistence and network call recovers without duplicate submission; ambiguous outcome stays `UNKNOWN`.  
**Depends on:** P0.2.

## P0.4 Make risk reservations atomic

**Outcome:** concurrent signals cannot collectively exceed cash, margin, gross, net, or quantity limits.  
**Evidence:** concurrency test with shared account partition rejects the second reservation deterministically.  
**Depends on:** P0.2.

## P0.5 Implement fill reducer and full reconciliation

**Outcome:** duplicate, delayed, out-of-order, and overfill events cannot corrupt state.  
**Evidence:** order, position, cash, average price, fees, multiplier, and PnL projections reconstruct identically after restart and compare fully with broker truth.  
**Depends on:** P0.2 and P0.3.

## P0.6 Fail closed on bad inputs and unknown state

**Outcome:** stale/malformed market data, feature failure, account read failure, unknown submission, and unresolved reconciliation prevent new entries.  
**Evidence:** no path returns valid-looking zero/empty fallback for a failed capital or market-data read.  
**Depends on:** P0.2 and unified readiness design.

## P0.7 Close security blockers

**Outcome:** production rejects plaintext token storage; webhook requests are signed and replay-protected; sensitive mutations require scoped authorization; audit is durable before mutation.  
**Evidence:** negative tests prove insecure configuration and unauthorized mutation fail.  
**Depends on:** P0.2 for audit identity.

## P0.8 Repair validation truthfulness

**Outcome:** CI scans `src/`, uses current paths, and reports skipped/not-run critical suites distinctly. Security, type, architecture, parity, and persistence gates are blocking.  
**Evidence:** deliberately broken boundary and skipped critical suite fail promotion.  
**Depends on:** P0.2 and P0.6.

## P0.9 Route replay, backtest, and Paper through the reducer

**Outcome:** simulation modes produce projections through the same state transitions; only event source/fill model vary.  
**Evidence:** identical event trace produces equivalent order/fill/position/PnL state across modes under the same declared fill policy.  
**Depends on:** P0.5.

## P0.10 Broker ambiguity and recovery evidence

**Outcome:** Dhan and Upstox demonstrate unknown-write resolution, reconnect, partial-fill, stream freshness, account refresh, and restart reconciliation through typed adapters.  
**Evidence:** real read-only/sandbox workflows pass without mocks or fabricated market data.  
**Depends on:** P0.3, P0.5, P0.6, and ACL migration.

## Exit gate

P0 is complete only when no money-moving state has multiple authoritative owners, no external failure is collapsed into success, and a restart/reconciliation drill proves the account returns to the same economic state before new entries become enabled.
