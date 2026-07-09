# Safe-to-Trade Gate + Sequencing (P0)

**Status:** In progress (2026-07-09)  
**Mode:** Execute Phases 0–1 first; object-model completion **after** gate is green.  
**Basis:** User plan (safe-to-trade + full redesign) + review docs  
[`docs/INSTITUTIONAL_ARCHITECTURE_REDESIGN.md`](../docs/INSTITUTIONAL_ARCHITECTURE_REDESIGN.md),  
[`docs/ARCHITECTURE_REVIEW_PART2_FULL.md`](../docs/ARCHITECTURE_REVIEW_PART2_FULL.md).

Related product design (runs **after** this gate):  
[`OBJECT_MODEL_COMPLETION_DESIGN.md`](./OBJECT_MODEL_COMPLETION_DESIGN.md).

---

## Sequencing (locked)

```text
Phase 0  Boot & security blockers     ← P0-A…P0-K
Phase 1  Order safety gate            ← P0-G… orphan / recon / connect kernel
──────── safe-to-trade gate green ────────
Phase 2  Backtest / PnL collapse
Phase 3  Single pipeline & event bus
Phase 4  Packaging & CI
Phase 5  DX polish
──────── then ────────
Object-model PRs (PR-0…PR-6 in OBJECT_MODEL_COMPLETION_DESIGN)
```

---

## Phase 0 — Boot & security (status)

| ID | Finding | Status | Notes |
|----|---------|--------|-------|
| **P0-A** | API `validate_production_config` missing | **Done** | `runtime/production_config.py` implements it; `create_app` boots |
| **P0-B** | `.env.local` git-tracked | **Done (index)** | In `.gitignore`; staged `git rm --cached`. **Manual:** rotate Dhan secrets; optional history scrub (`git filter-repo`) is operator-run only |
| **P0-C** | Auth fail-open | **Done** | Only `api_key` (+ test/local `none` with `TRADEX_ALLOW_AUTH_NONE=1`); docs gated in prod; WS key header-only |
| **P0-J** | Client-chosen live broker | **Done** | Server resolves via `load_trading_config().primary_broker` |
| **P0-K** | Kill-switch any key | **Done** | `require_admin` on `/risk/kill-switch` and live extended kill-switch |

**Success criteria (Phase 0):**

- [x] `create_app()` boots  
- [x] `.env.local` not in `git ls-files`  
- [x] Invalid `AUTH_MODE` rejected; `none` blocked in prod  
- [x] Orders ignore client broker query  
- [x] Kill-switch requires admin  

---

## Phase 1 — Order safety (status)

| ID | Finding | Status | Notes |
|----|---------|--------|-------|
| **P0-G** | ExecutionComposer bypasses OMS | **Done** | Requires `risk_manager` + `order_manager`; place/cancel/modify via OMS |
| **P0-H** | Dedup eviction double-position | **Done** | Hot set may age-evict; **durable set + JSONL never forget**; `is_processed` consults durable. Default `PROCESSED_TRADE_RETENTION_SECONDS=0` (no hot eviction) |
| Wave1 P0-4 | Trade-before-order race | **Done** | `_pending_trades_by_order` buffer + flush on order arrival |
| **P0-I** | `connect()` skips quota/router | **Done** | `wire_gateway_for_session` registers registry+quota+router; `session.kernel` attached |
| Orphan submit | submit-then-exception | **Done enough** | Record-then-submit stub + `_release_pending` on exception |
| Recon heal | report-only default | **Done** | `application/oms/recon_heal_policy.py`; `TRADEX_RECONCILIATION_AUTO_REPAIR=1` enables correct-then-heal; CLI never bypasses OMS |
| Order-path parity | multi-entry OMS | **Done** | `application/oms/tests/test_order_path_parity.py` |

**Success criteria (Phase 1):**

- [x] Parity test: OMS core / SDK `OmsOrderService` / CLI-style / ExecutionComposer → idempotency + risk kill-switch + audit  
- [x] Redelivery after hot eviction does not double-position (unit covered)  
- [x] Reconciliation heal path exercised (`auto_repair=True` upserts missing order; default report-only)  
- [x] CLI `BrokerService.place_order` fails closed without TradingContext (no bare gateway)  

---

## Gate status

**Phases 0–1 money-path criteria: green for unit/component tests.**

Remaining non-blocking follow-ups (Phase 2+ / ops):

1. Full FastAPI HTTP-level order parity (needs app DI + auth fixture) — spine is covered via `OmsOrderService` (same as API `session.place`)  
2. Operator: **rotate** any secrets that were ever committed; history scrub if required by policy  
3. Phases 2–5 of institutional redesign (backtest collapse, pipeline, packaging)

**Object-model PR-1+ may proceed** once this file’s Phase 0–1 checkboxes stay green in CI.

### Object-model progress (post-gate)

| PR | Status |
|----|--------|
| PR-0 API v2 history `HistoricalSeries` | **Done** |
| PR-1 lazy provider + AmbientSession + safe close | **Done** |
| PR-2 InstrumentHistory facade | **Done** |
| PR-3 instrument.buy OMS-only + Universe stamp | **Done** |
| PR-3b OptionChain OMS stamp | **Done** |
| PR-4 Future/Option pure math | **Done** |
| PR-5+ asset types | Gated (identity/exchange) |
| PR-6 docs/examples | **Done** — `docs/OBJECT_MODEL.md`, `examples/object_model_quickstart.py` |
---

## Manual operator steps (not automated)

```bash
# Confirm secrets untracked
git ls-files .env.local   # must print nothing

# Rotate Dhan access token / TOTP secrets that may have leaked historically
# Optional history rewrite (destructive — coordinate with team):
#   git filter-repo --path .env.local --invert-paths
```

---

## Linkage to object-model design

After the gate:

| Object-model PR | Depends on gate |
|-----------------|-----------------|
| OM PR-0 API history fix | Phase 0 API boot |
| OM PR-1 provider ambient | Phase 1 connect kernel OK |
| OM PR-3 instrument.buy OMS-only | **Phase 1 P0-G spine** mandatory |
| OM PR-4 math | independent of money path |
