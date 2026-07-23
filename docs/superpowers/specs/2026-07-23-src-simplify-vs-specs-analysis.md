# Can `src/` Be Simplified Toward `specs/` Without Losing Features?

> **Date:** 2026-07-23  
> **Scope:** `src/` only (ignore any parallel tree). Specs = `specs/IMPLEMENTATION-SPEC.md` + numbered docs 00–15.  
> **Question:** Is it possible to reshape the existing application into the simpler Nautilus-style shape described in specs **without compromising features or functionality already delivered in `src/`?**  
> **Verdict (short):** **Partial yes for structure; no for a wholesale “become the spec tree.”** In-place simplification can cut accidental complexity and enforce the single spine the specs demand. It cannot make `src/` look like a ~50-file broker framework while keeping today’s broker/API/analytics surface intact—unless you redefine “feature” to exclude large parts of what already ships.

---

## 1. System Intent

### Specs (target intent)

Specs describe a **framework-shaped** trading kernel:

- MessageBus is the **sole** inter-component channel.
- One **ExecutionEngine** spine; zero bypass order paths.
- Four-mode parity (Replay / Backtest / Paper / Live) via FillSource + Clock only.
- Brokers as thin **Gateway → Connection → 5 sub-adapters** (~50 focused plugin files total).
- No god classes (dependency degree ≤ 50).
- Analytics-first surfaces over a small composition root (`TradingNode`).

Specs are explicitly **target product / greenfield contracts**, not as-built docs (`specs/README.md`).

### `src/` today (actual product intent, from `context/`)

`src/` is a **mature application** (~159k LOC, ~1,166 Python files) that already implements:

- Analytics-first CLI + FastAPI + TUI + MCP.
- DuckDB/Parquet datalake, scanners, indicators, options/futures research.
- OMS + Risk + ExecutionTarget (paper/replay/backtest focus; live money still gated).
- Dhan / Upstox / Paper with rich auth, streaming, instruments, rate limits.
- Large architecture-test ratchet suite.

Context still mandates **evolutionary refactor of `src`, not rewrite**, and protects `src/domain/` without ADR.

### Expected Behavior Contract (for this analysis)

| Dimension | Contract |
|-----------|----------|
| **Inputs** | Specs’ architectural constraints + inventory of what `src/` operators can do today |
| **Outputs** | Feasibility map: safe simplify / risky reshape / do-not-touch |
| **Timing** | No claim that a “10-week greenfield” applies to in-place work |
| **State transitions** | Simplification must preserve order FSM, risk gate, idempotency, zero-parity simulation |
| **Failure modes** | Silent dual paths, split-brain OMS, broker-tree deletion that drops streaming/auth edge cases |

---

## 2. Current Architecture Map (`src/`)

### Size (order of magnitude)

| Area | ~Python files | Notes |
|------|---------------|--------|
| Total `src/` | ~1,166 | ~159k LOC |
| `brokers/` | ~307 | Dominant cost center |
| `brokers/providers/` | ~243 files / ~36k LOC | Canonical Dhan/Upstox/Paper tree |
| `brokers/{dhan,upstox,paper,common}/` | ~37 files / ~2.6k LOC | Residual / thinner layout — **dual tree smell** |
| `domain/` | ~239 | Large; ports alone ~51 modules |
| `interface/` | ~152 | API ~58 + UI ~93 |
| `analytics/` | ~121 | pipeline + views + engines + scanners |
| `application/` | ~111 | OMS, execution, composer, trading, streaming, … |
| `infrastructure/` | ~106 | Event bus, auth, resilience, observability |
| `datalake/` | ~68 | Ingestion, gateway, quality, catalog |
| `runtime/` | ~34 | ProcessKernel + many compose helpers |

### Control plane (composition)

Intended sole root: `ProcessKernel.wire()` / `ProcessKernel.boot(mode)` (`src/runtime/kernel.py`).

Still present as compatibility / alternate builders:

- `runtime.factory.build` / `build_from_broker_service`
- `runtime.api_compose.build_for_api`
- `runtime.paper_session.build_*`
- `runtime.broker_infrastructure.build_infrastructure`
- UI `build_runtime`, session bridges, etc.

**Actual:** single *declared* root, multiple *live* build paths. Specs want one `RuntimeFactory` / `TradingNode`.

### Order / execution spine

Declared convergence: `place_order_spine` → `OrderManager.place_order(..., submit_fn=target.submit_fn())`.

Architecture ratchet (`tests/architecture/test_place_order_path_inventory.py`) still **allowlists** multiple application/interface entry points:

- `OrderManager`, `ExecutionEngine`, `ExecutionComposer`
- API `orders` router, CLI order placement, `BrokerService`
- Many broker wire `place_order` surfaces

**Actual:** spine exists; “no bypass” is **ratcheted allowlist**, not yet the specs’ absolute invariant.

### Message bus

`EventBus` exists and is a major hub (graph degree ~252). Also present: `AsyncEventBus`, persistence hooks, DLQ, processed-trade repo, separate `BufferedEventLog`.

**Actual:** bus is central for many flows, **not** the sole inter-component channel (composers, orchestrators, and direct service calls remain).

### Brokers

Specs target ~50 files, Gateway→Connection→5 adapters.

`src` has ~300+ broker modules, deep websocket/auth/instrument stacks, and a providers tree that alone exceeds the entire target broker budget.

---

## 3. End-to-End Execution Flow (as `src` runs)

### Research / simulation path (must keep)

```
CLI/API → ProcessKernel / paper_session
  → Market data (broker MD or datalake)
  → FeaturePipeline / scanners / strategy
  → TradingContext (OMS + Risk)
  → ExecutionEngine / place_order_spine
  → PaperFillSource | SimulatedFillSource | Replay path
  → Position/PnL + analytics reports
```

### Operator live-data path (must keep)

```
Broker WS/REST → wire normalize → EventBus / cache
  → analytics / TUI / API market routes
  → (orders only via OMS spine when execution enabled; live still gated)
```

### Specs’ ideal path

```
TradingNode → MessageBus → StrategyEngine → RiskGate → ExecutionEngine → FillSource
  ← durable MessageLog for Replay
```

**Mismatch:** specs assume framework-calls-user-code; `src` is still largely application-calls-engine with many facade layers (`ExecutionComposer`, `TradingOrchestrator`, `BrokerService`).

---

## 4. Spec Goal vs `src` Reality (capability lens)

Specs’ 147 capabilities are **COVERED as specification**, not as “already implemented thin.” Mapping for simplification:

| Spec theme | In `src` today? | Simplify without feature loss? |
|------------|-----------------|--------------------------------|
| Single ExecutionEngine spine | Partially (spine + allowlist) | **Yes** — collapse facades onto spine |
| MessageBus sole channel | Partial hub, not sole | **Risky** — full bus-only rewrite touches every feature |
| Four-mode FillSource matrix | Present (paper/sim/replay; live gated) | **Yes** — clarify mode matrix; do not fake LIVE |
| Gateway→Connection→5 adapters | Buried inside large providers | **Partial** — reorganize; cannot shrink to ~50 files without dropping code |
| TradingCache as authority | Split across OMS context / caches | **Yes** — consolidate views, keep behavior |
| Durable MessageLog replay | Event log / replay engines exist | **Partial** — unify logs; don’t delete analytics replay |
| Analytics suite | Very large (`analytics/` + datalake views) | **Do not delete** — dual pipeline/views is intentional parity work |
| Broker auth/TOTP/rate limits | Deep, production-hardened | **Keep** — “thin broker” must still host this complexity |
| God-class limit ≤50 degree | EventBus, brokers, orchestrators are hubs | **Partial** — split facades; hubs will remain |
| TradingNode public API | Session / ProcessKernel / CLI compose | **Yes** — thin façade over existing kernel |

---

## 5. Invariant Checklist

| # | Invariant | Specs | `src` enforcement | Simplify risk if weakened |
|---|-----------|-------|-------------------|---------------------------|
| 1 | Zero-parity OMS/Risk across sim modes | Required | Strong goal; paper/replay hooks intentional deltas (ADR-0024) | High |
| 2 | Single composition root | Required | ProcessKernel declared; shims remain | Medium |
| 3 | No order bypass of RiskGate + OMS | Required | Allowlist ratchet | **Critical** |
| 4 | Domain purity | Required | import-linter + arch tests | High |
| 5 | Runtime-only concrete brokers | Required | Mostly; UI BrokerService still thick | Medium |
| 6 | Paper-first / live gated | Context ADR-0012 | Enforced | Do not “simplify” by opening live |
| 7 | No mock on money path | Required | CI checks | High |
| 8 | Broker plugins independent | Required | Large shared + dual trees | Medium |

---

## 6. Failure & Risk Points (real-money / silent)

What can go wrong **silently** if simplification is naive:

1. **Deleting “duplicate” order entry points** without proving they all call `place_order_spine` → API/CLI/backtest diverge (split-brain books).
2. **Collapsing EventBus variants** while replay/persistence hooks still depend on a specific bus → lost fills or non-deterministic replay.
3. **Trimming broker websocket stacks** to meet a file-count goal → depth/order stream gaps under load (real-time break).
4. **Merging pipeline vs DuckDB views** prematurely → research results change without a failing unit test (parity gate exists for a reason).
5. **Moving auth/TOTP into a “thin” helper** without cooldown/JWT probe semantics → mint storms / lockouts.
6. **Assuming MessageBus-only communication** while composers still mutate OMS state directly → race and ordering bugs under concurrent WS + REST.
7. **Unsafe assumptions:** “specs file count = correctness”; “unused-looking broker module is dead”; “interface BrokerService is just a UI helper.”

**Implicit vs explicit today**

- Explicit: `place_order_spine`, ProcessKernel, ADR live gates, place_order path inventory.
- Implicit: which of the many `build_*` paths is “the” production boot; how composer vs engine share OrderManager; when EventBus persistence is on.

---

## 7. Feasibility Verdict

### Can we “simply” the app as specs suggest?

| Interpretation | Possible? | Feature compromise? |
|----------------|-----------|---------------------|
| **A. Make `src/` directory layout and LOC match specs’ greenfield tree** | **No** (without rewrite) | Would drop or reimplement most of brokers/analytics/API |
| **B. Adopt specs’ *invariants* inside `src/` (single spine, one boot, thinner facades)** | **Yes** | No, if done with ratchets and parity tests |
| **C. Shrink brokers to ~50 files while keeping Dhan+Upstox behavior** | **No as stated** | Auth, streaming, instruments, wire, rate limits *are* the feature surface; they need code |
| **D. MessageBus as sole channel everywhere** | **Not without multi-quarter rewrite** | High risk of silent ordering/regression |

**Bottom line:** Specs’ *shape* is a useful north star for **deleting accidental layers** in `src/`. Specs’ *size targets* are a greenfield fantasy relative to this codebase. Simplification without feature loss = **B**, not A/C/D.

---

## 8. Proposed Approaches (src-only)

### Approach 1 — Invariant-first squeeze (recommended)

**Do:** Enforce specs’ hard invariants inside existing packages; delete facades that don’t add behavior.

1. Finish migrating all boots to `ProcessKernel`; delete or stub-forbid alternate roots.
2. Shrink place_order allowlist until only spine + broker wire + domain ports remain.
3. Make `ExecutionComposer` / CLI `BrokerService` pure delegates (no parallel OMS state).
4. Keep analytics/datalake/brokers; reorganize brokers toward Gateway→Connection→adapters **without** LOC quotas.
5. Unify “which EventBus” at composition time; keep persistence hooks.

**Pros:** Preserves features; aligns with context “evolutionary”; matches existing ratchets.  
**Cons:** Tree still large; won’t “look like” the spec folder diagram.

### Approach 2 — Package surgery (layout match)

**Do:** Physically move `brokers/providers` → `plugins/brokers`, carve shared/, rename EventBus→MessageBus, etc.

**Pros:** Specs-shaped paths.  
**Cons:** Mass import churn; high regression cost; **no** inherent simplification; easy to break money paths.  
**Not recommended** as the primary strategy.

### Approach 3 — Capability freeze + aggressive deletion

**Do:** Declare large CLI/API/analytics subsets out of scope and delete to hit size goals.

**Pros:** Smaller tree.  
**Cons:** Explicitly compromises features — fails the user’s constraint.

---

## 9. Proposed Correct Architecture (for `src` simplification)

Keep current packages; change **ownership and paths**:

```
interface/     → presentation only; no OMS state
runtime/       → ProcessKernel ONLY builds; resolves FillSource/Clock/Broker once
application/   → OrderManager + Risk + ExecutionEngine + TradingOrchestrator
                 (Composer = adapter to spine, not second OMS)
infrastructure/→ one EventBus impl (+ hooks), auth, resilience
brokers/       → Gateway→Connection→adapters (behavior preserved; files as needed)
analytics/     → research engines; publish intents via bus/spine only
datalake/      → storage/quality; exchange calendar via plugin
domain/        → ports/entities unchanged without ADR
```

**Delete candidates (only after call-graph proof):**

- Dead dual broker modules under thin `src/brokers/{dhan,upstox}/` if unused by providers.
- Duplicate compose helpers once ProcessKernel owns all modes.
- Non-spine order helpers that only wrap the same `place_order`.

**Never delete on size grounds alone:** websocket feeds, TOTP/JWT ensure, rate limit windows, reconciliation, parity tests, datalake sync.

---

## 10. Migration Plan (minimal but correct)

Phased, each phase feature-preserving and ratchet-gated:

| Phase | Change | Exit gate |
|-------|--------|-----------|
| **P0** | Inventory: boot paths, order paths, broker dual-tree reachability | Written matrices + arch tests updated |
| **P1** | ProcessKernel exclusivity — deprecate `factory.build*` public use | `test_single_composition_root` + no new callers |
| **P2** | Order path collapse — composer/CLI/API → spine only | Allowlist shrink; OMS singleton tests green |
| **P3** | Broker layout — single tree; Gateway/Connection naming; no behavior drop | Adapter harness + live smoke (when creds) |
| **P4** | Bus unification — one bus instance policy; document non-bus sync calls that remain | Replay determinism + event persistence tests |
| **P5** | Facade diet — TradingOrchestrator/BrokerService LOC via extract, not rewrite | Same CLI/API contracts; coverage floors hold |

Stop and redesign if any phase needs **>2 local patches** to keep parity (per real-money review rule).

---

## 11. What Specs Suggest That `src` Should *Not* Copy Blindly

1. **“~50 broker files”** — treat as *module cohesion* guidance, not a budget that overrides Indian broker reality.
2. **Greenfield 10-week phases** — invalid for in-place; use the phase table above.
3. **LIVE as equal peer in day-one parity** — context still NO-GO; simplifying must not imply live lift.
4. **Framework-calls-strategy purity** — adopt gradually; do not break working strategy/scanner CLIs overnight.

---

## 12. Explicit Answers (reviewer checklist)

| Question | Answer |
|----------|--------|
| What can go wrong silently? | Dual OMS paths, bus/persistence mismatch, “dead” broker code that still serves a stream, view/pipeline drift |
| What breaks under real-time conditions? | Over-thinned WS/auth/rate-limit; sync bridges (`asyncio.run`) if facades are “simplified” incorrectly |
| What assumptions are unsafe? | Specs size = simpler product; file count reduction = same features; MessageBus-only is a small change |
| Where is behavior implicit? | Which `build_*` is production; composer vs engine ownership; when EventBus persistence is active |

---

## 13. Recommendation

**Proceed with Approach 1 (invariant-first squeeze) on `src/` only.**

- **Yes:** simplify *control flow and ownership* to match specs’ invariants without feature loss.  
- **No:** expect `src/` to become the specs’ small greenfield tree without discarding capability.  
- **Document success as:** fewer boot paths, zero non-spine application order entries, one broker tree, unchanged CLI/API/analytics/datalake operator outcomes.

---

## 14. Spec Self-Review Notes

- No TBDs left for the feasibility question; implementation sequencing is intentionally high-level until P0 inventories are run as code.
- Scope limited to `src/` + `specs/` as requested.
- Ambiguity resolved: “features” = what `src/` already delivers under `context/` (including gated live), not a mandate to enable live money to match specs’ LIVE chapter.
