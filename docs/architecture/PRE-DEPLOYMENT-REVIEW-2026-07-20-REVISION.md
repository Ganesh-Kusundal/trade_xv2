# TradeXV2 — PRE-DEPLOYMENT Review Revision

**Date:** 2026-07-20 (post Architecture Maturity Program implementation)  
**Prior:** [`PRE-DEPLOYMENT-REVIEW-2026-07-20.md`](PRE-DEPLOYMENT-REVIEW-2026-07-20.md) (~5.0/10)  
**Method:** Constitution Contexts 5–6, 8, 10 delivered; new ratchet tests green

---

## Decision

| Surface | Score | Verdict |
|---|---|---|
| Paper / research | **8.0 / 10** | **Conditional GO** |
| Live money | **6.8 / 10** | **NO-GO** (ADR-0012 unchanged) |

Live ADR lift blocked until paper ≥ **7.5** (met) **and** weekly chaos green for 4 consecutive weeks (not yet demonstrated).

---

## Dimension Revisions

| Dimension | Was | Now | Delta driver |
|---|---|---|---|
| OMS spine integrity | 6.0 | **7.5** | Acceptance suite + runtime OMS composition |
| Zero-parity defaults | 5.5 | **8.0** | Quote fail-closed; StrategyEvaluator bridge; coalesce in CandidateEvaluator |
| Kernel composition | 5.0 | **7.0** | `ServiceRegistry`; single `runtime/oms_composition` bootstrap |
| Event reliability | 5.0 | **8.0** | `EventDispatchHook` (GC-01); DP-04; ResilientHttpTransport wired (DP-01) |
| Testing maturity | 5.5 | **8.0** | Broker fill acceptance; fail-open ratchet; order port ratchet |
| Production hardening | 4.0 | **7.5** | Metrics auth profile-scoped (SEC-004/005); fail-open ratchet; weekly hardening 243 tests green locally |

**Weighted overall (paper): 8.1 / 10** — post sprint (OE-01, SEC metrics, GC-01, local hardening)
**Weighted overall (live): 6.8 / 10** — ADR-0012 lift still blocked (chaos 0/4, live < 8.5)

---

## Deliverables Shipped

1. [`docs/constitution/10-architecture-maturity-program.md`](../constitution/10-architecture-maturity-program.md) — hybrid model, logical packages, phase map
2. `runtime/service_registry.py`, `runtime/oms_composition.py`, `runtime/tick_authority.py`
3. `CapitalMetricsLabel` + `capital_metrics_valid` on `BacktestResult`
4. Architecture ratchets: `test_research_mode_gating`, `test_tick_authority`, `test_service_registry`
5. Acceptance: `tests/acceptance/oms/test_paper_fill_acceptance.py`
6. CI: `.github/workflows/weekly-hardening.yml`

### Next Maturity Contexts (2026-07-20)

7. DP-04: `should_publish_tick_directly()` gates Dhan/Upstox broker-direct TICK; reconnect disconnect-before-reopen
8. Quote-zero fail-closed: `QuoteUnavailableError` in `runtime/factory` + `runtime/paper_session` (no phantom zero-price fills)
9. Deploy-profile auth: `validate_production_config(surface='api')` requires `AUTH_MODE=api_key` + `API_KEY` in prod/staging only
10. Context 7: `analytics/strategy/evaluator_bridge.py` + orchestrator wiring + coalesce in `CandidateEvaluator`
11. Ratchets: `test_tick_authority`, `test_quote_fail_closed`, `test_deploy_profile_auth_unbypassable`, `test_strategy_evaluator_bridge`

### Live ADR Readiness Roadmap (2026-07-20)

12. **Phase 1a:** `BrokerFillSource` cancel/modify/capabilities + `test_broker_fill_acceptance.py`
13. **Phase 1b:** `test_production_fail_open_unbypassable.py` (RISK_FAIL_OPEN, SKIP_PARITY_GATE)
14. **Phase 2 (GC-01):** `EventDispatchHook` extracted from `EventBus`
15. **Phase 3a (DP-01):** Dhan + Upstox wired to `ResilientHttpTransport` rate-limit shell
16. **Phase 3b (SS-02):** `domain/ports/order_placement.py` + `test_order_placement_port.py`
17. **Phase 4:** `CredentialResolver` canonical in `gateway/factory.resolve_env_path`; `completeness_pct` via quality contract; OE-01 decision in [`OE-01-views-pipeline-ownership.md`](OE-01-views-pipeline-ownership.md)

### Live ADR Sprint (2026-07-20, multi-agent)

18. OE-01 golden parity: `tests/integration/quant/test_views_pipeline_parity.py`
19. SEC-004/005: `require_metrics_auth` prod/staging only + `test_metrics_auth_profile_scoped.py`
20. GC-01 complete: alerting loop on `EventBusAlertingService` only
21. SS-02: `invoke_place_order` + Dhan/paper transport wiring
22. Local weekly-hardening equivalent: **243 passed** (OMS + chaos + memory + architecture)
23. ADR-0013 lift preconditions doc

---

## Remaining Before Live

1. ~~DP-04 reconnect / single tick source under failover~~ **DONE**
2. ~~Quote-zero fail-closed on paper fills~~ **DONE**
3. ~~SEC deploy-profile auth (profile-scoped; dev `AUTH_MODE=none` unchanged)~~ **DONE**
4. ~~Context 7 StrategyEvaluator production bridge~~ **DONE**
5. 4× weekly chaos green on `main` (clock started — workflow exists; 0/4 demonstrated)
6. Explicit ADR lift of ADR-0012 (governance — not auto from green tests)
7. ~~Live FillSource full surface (cancel/modify/capabilities)~~ **DONE**
8. PRE-DEPLOY live dimensions ≥ 8.5 (current ~5.8; blocked on chaos clock + ADR lift)

---

## Exit Gate for Live ADR

All required:

- [x] Paper PRE-DEPLOY ≥ 7.5
- [ ] Weekly chaos + memory green × 4 weeks (0/4; `.github/workflows/weekly-hardening.yml` active)
- [x] DP-04 single tick authority under reconnect
- [x] Quote-zero fail-closed on paper fills
- [x] Deploy-profile API auth (prod/staging)
- [x] Context 7 StrategyEvaluator bridge
- [x] Live FillSource full surface (cancel/modify/capabilities)
- [x] No production fail-open capital paths (ratchet + `validate_production_config`)
- [ ] PRE-DEPLOY live dimensions ≥ 8.5
- [ ] Explicit ADR-0012 lift (requires 4/4 chaos + live ≥ 8.5)
