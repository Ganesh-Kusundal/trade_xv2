# Epic 1 — Market Access: Implementation Plan

**Status:** **Done for delivery** (2026-07-09) — MA-S1 + MA-S2 + **MA-024 stream fix (W2)**; gated live subscribe smoke added  
**Date:** 2026-07-09  
**Constitution:** [`docs/OPERATING_MODEL.md`](../docs/OPERATING_MODEL.md)  
**Backlog:** [`ENGINEERING_BACKLOG.md`](./ENGINEERING_BACKLOG.md) (MA-*)  
**Objective:** Ship the **smallest end-to-end, production-ready market-data slice** with minimal disruption.

### Decisions locked at execution

| # | Decision | Choice |
|---|----------|--------|
| D1 | Live broker for MA-S2 | **dhan** |
| D2 | Subscribe for Epic 1 exit | Paper required ✅; live WS deferred (MA-024) — **accepted for Epic 1 exit** |
| D3 | CI live tests | Opt-in / skip without `.env.local` |
| D4 | Depth in MVP | Stretch only (not required) |

### Closeout decision (T4 Market data — 2026-07-09)

**Epic 1 is closed.** MA-024 is **not** implemented in this closeout:

1. Live product-path subscribe is **not** a cheap 30-minute test: `DhanDataProvider.subscribe` kwargs do not match `DhanBrokerGateway.stream`, errors are swallowed, and ticks are not normalized to `QuoteSnapshot` for `Instrument` state.
2. Live WS is credentials + network + market-hours dependent; not a reliable default CI path without a new harness.
3. Paper subscribe (MA-012) remains the CI-backed subscribe proof per D2.
4. Re-open MA-024 only when live stream work is already in blast radius (or a dedicated gated L3 slice is scheduled). Do **not** reopen Epic 1 foundations for this stretch.

---

## 1. Capability statement

A developer or operator can:

1. Connect to a session (`tradex.connect`)
2. Resolve a liquid equity (and optionally an index) via `session.universe`
3. Fetch a **quote** into instrument state (`refresh`)
4. Fetch **historical bars** (`history`)
5. **Subscribe** to live updates (paper simulated or live WS) and unsubscribe cleanly
6. Close the session without resource leaks

Without importing broker gateways or knowing transport details.

### Explicitly out of scope for Epic 1

| Out of scope | Belongs to |
|--------------|------------|
| Place / modify / cancel orders | Epic 2 |
| Positions / portfolio / PnL | Epic 2 |
| Option chain / Greeks productization | Epic 3 |
| Scanner / backtest features | Epic 4 |
| Strategy automation | Epic 5 |
| Broker tree rewrites, CLI god-object split, full shim purge | Category C / rejected programs |
| Multi-broker parity matrix for every endpoint | Later slices; start with paper + **one** live broker |

---

## 2. Smallest shippable slice (MVP)

### MVP definition (recommended)

**Slice MA-S1 — Paper Market Access (CI-gated)**

```text
tradex.connect("paper")
  → universe.equity("RELIANCE")
  → refresh() → non-None QuoteSnapshot with ltp
  → history(timeframe="1D", days=5) → series with bars
  → subscribe() → handle; instrument state can update
  → unsubscribe / session.close() → clean
```

**Why paper first:** no credentials, deterministic CI, proves public API and ports without live flakiness.

### Slice MA-S2 — Live market-data path (gated / manual or opt-in CI)

```text
tradex.connect("<live_broker>", mode="market")
  → same object API as paper
  → orders disabled (ConnectError / ORDERS_DISABLED if attempted)
  → quote + history + subscribe for one symbol (e.g. RELIANCE / NSE)
```

**Live broker choice:** pick the broker that already has the strongest `DataProvider` + instrument resolution path (inspect at implementation time; candidates `dhan` / `upstox`). Do **not** implement both live brokers in the same slice unless the second is free (already green).

### Success metric

- MA-S1 green on every PR  
- MA-S2 documented + reproducible with env file; automated if secrets available in gated job, else manual checklist signed off  

---

## 3. Existing reusable components (do not rebuild)

| Layer | Component | Path / symbol | Role |
|-------|-----------|---------------|------|
| Public SDK | `tradex.connect` / `open_session` | `tradex/session.py`, `tradex/__init__.py` | Composition root |
| Domain session | `Session`, `Universe` | `src/domain/universe.py` | `equity`, `index`, resolve, batch helpers |
| Instrument API | `Instrument.refresh/history/subscribe/depth` | `src/domain/instruments/instrument.py` | Product behaviors |
| Ports | `DataProvider` | `src/domain/ports/protocols.py` | Quote, history, depth, subscribe |
| Historical types | `HistoricalSeries`, bars | `src/domain/candles/historical.py` | History results |
| Quote model | `Quote` / `QuoteSnapshot` | domain entities + `docs/architecture/QUOTE_TYPES.md` | Mapping contract |
| Runtime | gateway factory, session wire-up | `tradex/runtime/gateway_factory.py`, `session_infra.py` | Broker construction |
| Runtime | MD gateway adapter | `tradex/runtime/adapters/market_data_gateway_adapter.py` | Bridge gateway → provider shape |
| Runtime | instruments helpers / registry | `tradex/runtime/instruments.py`, `services/instrument_registry.py` | Master data |
| Brokers | `DhanDataProvider` | `brokers/dhan/data_provider.py` | Live data adapter |
| Brokers | Paper gateway / providers | `brokers/paper/*` | Sim data |
| Brokers | Stream / subscription engines | e.g. `brokers/dhan/subscription_engine.py`, WS feeds | Live ticks |
| Domain | streaming service / handles | `src/domain/services/streaming.py` | Subscription semantics |
| Docs / examples | object model | `docs/OBJECT_MODEL.md`, `examples/object_model_quickstart.py` | User-facing path |
| Tests | connect factory, object model e2e, contracts | `tests/unit/test_tradex_connect_factory.py`, `tests/e2e/test_object_model.py`, `tests/contract/*`, `tests/unit/test_domain_port_contracts.py` | Extend, don’t replace |

**Principle:** Prefer wiring and tests over new abstractions. The product API largely exists; Epic 1 is **harden + prove + document**, not redesign.

---

## 4. Modules likely to touch

Touch set is intentionally small. Expand only if a failing acceptance test forces it.

### MA-S1 (paper) — expected touch set

| Module area | Why |
|-------------|-----|
| `tests/e2e/` or `tests/integration/` (new or extend) | Canonical market-access regression |
| `tests/contract/` or provider unit tests | DataProvider paper conformance gaps |
| `brokers/paper/*` | Only if paper quote/history/subscribe incomplete |
| `examples/object_model_quickstart.py` | Align example with MVP (data-first section) |
| `docs/OBJECT_MODEL.md` | Market-access section clarity |

### MA-S2 (live) — additional touch set (as needed)

| Module area | Why |
|-------------|-----|
| `tradex/session.py` | mode=`market` guarantees (orders off, data on) |
| Chosen broker `data_provider` + instrument id mapping | Quote/history resolution |
| WS subscribe path for that broker | Tick → `QuoteSnapshot` → instrument state |
| `tradex/runtime/adapters/*` | Mapping consistency only if broken |
| `.env.example` (not secrets) | Document required vars for market mode |
| Gated test module under `tests/integration/` or `tests/e2e/` | `@pytest.mark.live` or similar |

### Explicit non-touch (unless Category A appears)

- `application/oms/**` (orders not in Epic 1)  
- CLI `BrokerService` split  
- Full `brokers.common` shim deletion program  
- Analytics / datalake scanners  
- `TradingContext` redesign  

---

## 5. Production blockers to verify/fix first (Category A)

These are **gates before calling live market access “production-ready”**. Paper MVP can ship while live remains gated, but A-items must not be ignored.

| ID | Blocker | Check | Action if red |
|----|---------|-------|---------------|
| MA-090 | Secrets in repository | `.env.local` / tokens untracked; history clean; `.gitignore` | Remove from tree, rotate credentials, document env-only loading |
| MA-020 | mode=`market` must not require OMS | `tradex.connect(live, mode="market")` succeeds without process OMS | Fix connect path only — do not invent second session type |
| MA-020b | Orders disabled in market mode | `stock.buy` / `session.buy` fails closed | Assert error code; no silent submit |
| Auth fail-closed | Invalid/missing credentials | Connect fails with actionable `ConnectError` | Improve error remediation strings only as needed |
| No gateway leak in product path | Examples/docs | Ensure docs don’t teach gateway imports | Doc-only fix |

**Not Category A for Epic 1:** dual scanners, CLI structure, residual shims, EventBus scale.

---

## 6. APIs to stabilize (freeze for this epic)

Treat as **frozen product surface** for Market Access:

```python
tradex.connect(broker: str, *, mode: str | None = None, env_path=..., load_instruments: bool = True) -> Session

session.universe.equity(symbol: str, exchange: str = "NSE") -> Equity
session.universe.index(name: str, exchange: str = "NSE") -> Index
# optional if already stable:
session.resolve(display_or_id: str) -> Instrument

instrument.refresh() -> QuoteSnapshot | None
instrument.ltp / bid / ask / volume
instrument.history  # callable facade
instrument.history(timeframe: str = "1D", days: int = ...) -> HistoricalSeries | compatible
instrument.subscribe(callback=None, *, depth: bool = False) -> SubscriptionHandle | None
instrument depth()  # nice-to-have in same slice if already works

session.close()
session.status  # mode, phase, trace_id
```

### Stabilization rules

1. **No breaking renames** of the above during Epic 1.  
2. Return types may be tightened (e.g. always `HistoricalSeries`) only with tests + doc update.  
3. `Quote` vs `QuoteSnapshot`: adapters map broker → `Quote` at boundary, then `to_snapshot()` for instrument state (`docs/architecture/QUOTE_TYPES.md`). Do not add a third quote type.  
4. New helper methods are additive only if the MVP cannot be expressed with the freeze list.

---

## 7. Engineering improvements allowed (B/C only in touch set)

| Improvement | Class | When allowed |
|-------------|-------|--------------|
| Fix paper provider gaps for quote/history/subscribe | B | Required for MA-S1 |
| Fix instrument token resolution for live quotes | B | Required for MA-S2 |
| Align Quote→QuoteSnapshot mapping bugs | B | Failing tests |
| Dead code / confusing names in files already edited | C | Boy Scout |
| Import path prefer `tradex.runtime` in files already edited | C | Boy Scout |
| Extract new “MarketAccessService” facade | C | **Avoid** — Session/Instrument already are the facade |
| Unify all brokers’ WS stacks | C | **Out of scope** |

---

## 8. Tests to add

### MA-S1 (required)

| Test | Type | Asserts |
|------|------|---------|
| `test_market_access_paper_quote_history_subscribe` | e2e / integration | Full MVP path on paper |
| `test_paper_refresh_populates_ltp` | unit/integration | `refresh` updates `instrument.ltp` |
| `test_paper_history_bar_count` | unit/integration | history returns expected shape / min bars |
| `test_paper_subscribe_unsubscribe` | unit/integration | handle lifecycle; no exception on close |
| Extend DataProvider contract for paper | contract | `get_quote`, `get_history`/`get_history_series`, `subscribe` |

### MA-S2 (required for live “done”)

| Test | Type | Asserts |
|------|------|---------|
| `test_connect_market_mode_without_oms` | unit | no OMS_REQUIRED for mode=market |
| `test_market_mode_orders_disabled` | unit | buy fails closed |
| `test_live_quote_one_symbol` | gated integration | real or recorded fixture |
| `test_live_history_one_symbol` | gated integration | bars returned |
| `test_live_subscribe_receives_tick` | gated integration | optional timeout-based |

### Regression / architecture

| Test | Asserts |
|------|---------|
| Existing architecture / import-linter | Still green |
| No new product-layer imports of concrete gateways in examples | Doc + optional lint |

**Fixtures:** prefer in-memory / paper; for live, use env-gated tests; VCR/recorded HTTP only if already patterned in repo — do not invent a large recording framework for this epic.

---

## 9. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Paper path “works” but live mapping broken | False confidence | Explicit MA-S2 acceptance; don’t mark Epic 1 complete on paper alone if live is claimed |
| Instrument master data missing → empty quotes | Live MVP fails | `load_instruments=True` default; clear ConnectError/remediation; test resolution for one symbol |
| Subscribe resource leaks | Process instability | close/unsubscribe tests; session.close idempotent |
| Flaky live CI | Noise, ignored tests | Gate live tests; paper is merge gate |
| Scope creep into orders/OMS | Epic 1 becomes Epic 2 | Hard out-of-scope list; reject PR drive-bys |
| Quote type confusion | Wrong fields / None ltp | Enforce QUOTE_TYPES mapping in adapter tests |
| Credential mishandling | Security incident | MA-090 first; never commit `.env.local` |

---

## 10. Deliverables

1. **Green MA-S1 tests** in default CI  
2. **MA-S2** path documented (`OBJECT_MODEL.md` + env example); gated tests or signed manual script under `examples/` or `scripts/`  
3. **Updated quickstart** emphasizing data path before orders  
4. **Backlog updates:** MA-* items → `done` / residual `deferred` with reasons  
5. **No new architecture program** — only touch-set Boy Scout notes in PR description  

---

## 11. Acceptance criteria

### MA-S1 accepted when

- [x] `tradex.connect("paper")` + equity + `refresh` + `history` + `subscribe` + `close` passes automated test  
- [x] Example/docs run without gateway imports  
- [x] Default Epic 1 regression suite green  
- [x] No secrets introduced  

### MA-S2 accepted when

- [x] `mode="market"` connects without process OMS  
- [x] Orders fail closed in market mode  
- [x] One live symbol: quote + history succeed with valid credentials (Dhan gated test)  
- [x] Live subscribe deferred explicitly as MA-024 (paper subscribe covers CI)  
- [x] Failure modes use ORDERS_DISABLED / ConnectError paths already in product  

### Epic 1 complete when

- [x] MA-S1 + MA-S2 (quote/history) acceptance met  
- [x] Delivery backlog Epic 1 slices closed or explicitly deferred  
- [x] Ready to start Epic 2 without reopening market-data foundations  
- [x] **2026-07-09 closeout:** Epic 1 marked **done for delivery**; MA-024 stays `deferred` with justification in backlog  

### Implementation notes (2026-07-09)

- **Root cause fixed:** `PaperDataProvider.get_history` called `PaperGateway.history(..., interval=...)` (invalid kwarg); exceptions swallowed → empty history. Now passes `timeframe` + `lookback_days`; added `get_history_series`.
- **Paper subscribe:** delivers one initial `QuoteSnapshot` so instrument state updates.
- **Tests:** `tests/e2e/test_market_access.py`, `brokers/paper/tests/test_data_provider_history.py`, live `test_L_DHAN_MARKET_ACCESS_QUOTE_HISTORY`.
- **MA-024 (deferred):** Product-path live WS needs stream-signature fix + Quote→QuoteSnapshot wrap + gated L3 test; not done in Epic 1 closeout. Paper subscribe covers CI.

---

## 12. Implementation sequence (historical — completed)

```text
0. MA-090 secrets hygiene check (A) — quick
1. Spike: run existing quickstart + object model tests; list gaps vs MVP
2. MA-S1: fill paper gaps → tests → docs (ship)
3. Boy Scout only in files touched for MA-S1
4. MA-S2: verify market mode + orders disabled tests
5. MA-S2: live quote → history → subscribe for one broker
6. Gated tests + docs
7. Ship; reassess backlog; propose Epic 2 first slice plan
```

**Estimate mindset:** days, not weeks, if the object model is already as complete as docs claim. If discovery shows large paper/live holes, **narrow MVP** (e.g. quote+history first, subscribe as MA-S1b) rather than expanding architecture.

---

## 13. Open decisions (resolve at approval)

| # | Decision | Recommendation |
|---|----------|----------------|
| D1 | Which live broker for MA-S2? | Choose the one with working `DataProvider` + instrument load in current tree; document choice in backlog when locked |
| D2 | Is subscribe mandatory for Epic 1 exit? | **Yes** for paper; for live, prefer yes but allow documented deferral if WS is Category B blocked — then Epic 1 exit = quote+history live + paper subscribe |
| D3 | CI live tests? | Opt-in marker; default CI = paper only |
| D4 | Depth (`instrument.depth`) in MVP? | Optional stretch; not required for exit |

---

## 14. Approval gate

**Status:** Plan was approved and **implemented**. This section is retained for history only — it is **not** a current “wait for approval” gate.

Original approval checklist (met):

1. MVP slices MA-S1 / MA-S2 accepted as written (or edited here)  
2. Out-of-scope list accepted  
3. Live broker choice (D1) decided — **dhan**  
4. Team agrees Epic 1 is **capability delivery**, not broker consolidation  

**Delivery closed 2026-07-09** with MA-024 deferred (see closeout decision above and backlog).

---

*End of Epic 1 plan.*
