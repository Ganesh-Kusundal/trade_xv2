# TradeXV2 — Complete Project Documentation

> **Generated:** 2026-06-30 | **Version:** 2.1 | **Architecture:** Hexagonal / Clean Architecture

---

## Table of Contents

1. [Complete File Hierarchy Tree](#1-complete-file-hierarchy-tree)
2. [Architecture As-Is](#2-architecture-as-is)
3. [Application Flows](#3-application-flows)
4. [Cross-Cutting Concerns](#4-cross-cutting-concerns)
5. [Domain Object Details](#5-domain-object-detail)
6. [Event-Driven Framework Details](#6-event-driven-framework-details)
7. [Dependency Injection & Code Patterns](#7-dependency-injection--code-patterns)

---

## 1. Complete File Hierarchy Tree

```
Trade_XV2/
│
├── .import-linter.ini
├── .pre-commit-config.yaml
├── .gitattributes
├── .gitignore
├── .coverage
├── .env.example
├── .env.local
├── .env.upstox
├── .qodercli.json
├── ARCHITECTURE.md
├── ARCHITECTURE_REMEDIATION_COMPLETE.md
├── CHANGELOG.md
├── CHANGELOG_V2.1.md
├── CONTRIBUTING.md
├── README.md
├── SECURITY.md
├── agent.md
├── goal.md
├── api_server.py
├── conftest.py
├── endpoints.py
├── indices.py
├── pyproject.toml
├── requirements.txt
├── secrets_manager.py
├── test_all_cli.sh
├── tradex
├── uv.lock
├── verify_deps.py
│
├── .github/
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── dependabot.yml
│   └── workflows/
│       ├── architecture-enforcement.yml
│       ├── ci.yml
│       ├── dhan-regression.yml
│       ├── load-test.yml
│       ├── mutation_nightly.yml
│       ├── mutation_testing.yml
│       └── production_gate.yml
│
├── .qoder/
│   ├── settings.local.json
│   ├── rules/
│   │   └── rule1.md
│   ├── agents/
│   │   ├── architecture-reviewer.md
│   │   ├── broker-auditor.md
│   │   ├── code-reviewer.md
│   │   ├── deep-static-auditor.md
│   │   ├── eda-auditor.md
│   │   ├── principle-architect-reviewer.md
│   │   ├── production-readiness-reviewer.md
│   │   ├── quant-platform-orchestrator.md
│   │   ├── quant-platform-reviewer.md
│   │   ├── reliability-readiness-reviewer.md
│   │   └── testing-strategy-auditor.md
│   ├── plans/
│   │   ├── cache_lifecycle_execution_plan.md
│   │   ├── cli_performance_fix.md
│   │   ├── instrument_cache_architecture.md
│   │   └── symbol_resolution_architecture.md
│   ├── repowiki/
│   │   ├── en/
│   │   └── knowledge/
│   └── skills/
│       ├── caveman/
│       ├── dhanhq/
│       ├── diagnose/
│       ├── grill-me/
│       ├── grill-with-docs/
│       ├── improve-codebase-architecture/
│       ├── quant-platform-orchestrator/
│       ├── setup-matt-pocock-skills/
│       ├── tdd/
│       ├── to-issues/
│       ├── to-prd/
│       ├── trading-visualization/
│       ├── triage/
│       ├── ultra-plan/
│       ├── ultra-review/
│       ├── write-a-skill/
│       └── zoom-out/
│
├── docs/
│   ├── DATA_DICTIONARY.md
│   ├── IMPORT_DIRECTION_RULES.md
│   ├── UPSTOX_WIRE_FORMAT.md
│   ├── upstox_v2_deprecation_tracker.md
│   ├── upstox_verified_capabilities.md
│   ├── PROJECT_DOCUMENTATION.md          ← (this file)
│   ├── adr/
│   │   ├── 0001-keep-a-changelog.md
│   │   ├── ADR-001-domain-single-source.md
│   │   ├── ADR-002-gateway-contract.md
│   │   ├── ADR-003-broker-abstraction-audit.md
│   │   ├── ADR-003-reconciliation-engine.md
│   │   ├── ADR-004-batch-fetch-mixin.md
│   │   ├── ADR-005-severity-vocabulary.md
│   │   ├── ADR-006-exchange-resolution-layer.md
│   │   ├── ADR-007-oms-first-execution.md
│   │   ├── ADR-008-option-chain-domain-type.md
│   │   ├── ADR-009-execution-service-facade.md
│   │   └── template.md
│   ├── audits/
│   │   ├── CAPABILITY_COVERAGE_MATRIX.md
│   │   └── UPSTOX_REVALIDATION_EVIDENCE.md
│   ├── brokers/
│   │   └── upstox.md
│   ├── loop/
│   │   ├── 01_architecture_findings.md
│   │   └── MISSION_LOG.md
│   ├── security/
│   │   └── securityidaudit.md
│   └── specs/
│       └── BACKEND_API_SPEC.md
│
├── data/
│   ├── sectors/
│   │   ├── auto.csv
│   │   ├── banking.csv
│   │   ├── capitalgoods.csv
│   │   ├── cement.csv
│   │   ├── chemicals.csv
│   │   ├── consumerdur.csv
│   │   ├── consumerservices.csv
│   │   ├── finance.csv
│   │   ├── fmcg.csv
│   │   ├── infra.csv
│   │   ├── infrastructure.csv
│   │   ├── it.csv
│   │   ├── media.csv
│   │   ├── metals.csv
│   │   ├── misc.csv
│   │   ├── nifty_sector_mapping.csv
│   │   ├── oilgas.csv
│   │   ├── pharma.csv
│   │   ├── platform.csv
│   │   ├── power.csv
│   │   ├── realty.csv
│   │   ├── retail.csv
│   │   ├── services.csv
│   │   ├── telecom.csv
│   │   └── textiles.csv
│   └── universes/
│       ├── nifty50.csv
│       ├── nifty100.csv
│       ├── nifty200.csv
│       └── nifty500.csv
│
├── config/
│   ├── __init__.py
│   ├── README.md
│   ├── endpoints.py
│   ├── feature_flags.py
│   ├── indices.py
│   ├── schema.py
│   ├── secrets_manager.py
│   ├── validator.py
│   ├── profiles/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── dev.py
│   │   ├── prod.py
│   │   └── staging.py
│   └── tests/
│       ├── __init__.py
│       ├── test_feature_flags.py
│       ├── test_profiles.py
│       └── test_validator.py
│
├── domain/
│   ├── __init__.py
│   ├── capabilities.py
│   ├── capability_manifest.py
│   ├── enums.py
│   ├── exchange_segments.py
│   ├── field_mapping.py
│   ├── historical.py
│   ├── instrument_id.py
│   ├── instrument_resolver.py
│   ├── lifecycle_health.py
│   ├── market_enums.py
│   ├── parsing.py
│   ├── provenance.py
│   ├── reconciliation.py
│   ├── requests.py
│   ├── result.py
│   ├── runtime_hooks.py
│   ├── status_mapper.py
│   ├── status_normalizer.py
│   ├── stream_health.py
│   ├── symbols.py
│   ├── trading_costs.py
│   ├── types.py
│   ├── constants/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── defaults.py
│   │   ├── exchanges.py
│   │   ├── market.py
│   │   ├── observability.py
│   │   ├── resilience.py
│   │   ├── risk.py
│   │   └── timeouts.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── account.py
│   │   ├── alerts.py
│   │   ├── instrument.py
│   │   ├── market.py
│   │   ├── options.py
│   │   ├── order.py
│   │   ├── order_lifecycle.py
│   │   ├── position.py
│   │   └── trade.py
│   ├── events/
│   │   ├── __init__.py
│   │   └── types.py
│   ├── execution/
│   │   ├── __init__.py
│   │   └── sizing.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── features.py
│   │   └── trading.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── broker_gateway.py
│   │   ├── event_publisher.py
│   │   ├── margin_provider.py
│   │   ├── market_data.py
│   │   ├── observability.py
│   │   ├── oms_backtest_adapter.py
│   │   ├── risk_manager.py
│   │   └── strategy_evaluator.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── order_repository.py
│   │   └── position_repository.py
│   └── tests/
│       ├── test_bounded_cache.py
│       ├── test_domain_immutable.py
│       ├── test_domain_ports.py
│       ├── test_entities_contract.py
│       ├── test_exchange_segments.py
│       ├── test_provenance_historical_stream.py
│       ├── test_status_mapper_contract.py
│       ├── test_symbols.py
│       └── test_trading_costs.py
│
├── application/
│   ├── __init__.py
│   ├── backtest/
│   │   ├── backtest_service.py
│   │   └── tests/
│   │       └── test_backtest_service.py
│   ├── composer/
│   │   ├── __init__.py
│   │   ├── execution.py
│   │   ├── factory.py
│   │   └── market_data.py
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── cancel_order_use_case.py
│   │   ├── execution_mode_adapter.py
│   │   ├── execution_service.py
│   │   ├── factory.py
│   │   ├── gateway_submit.py
│   │   ├── oms_backtest_adapter.py
│   │   ├── place_order_use_case.py
│   │   ├── position_sizing.py
│   │   ├── simulated_fill.py
│   │   └── tests/
│   │       ├── test_execution_mode_adapter.py
│   │       ├── test_execution_mode_oms_parity.py
│   │       ├── test_execution_service.py
│   │       ├── test_gateway_submit.py
│   │       └── test_parity_characterization.py
│   ├── oms/
│   │   ├── __init__.py
│   │   ├── RECOVERY.md
│   │   ├── capital_provider.py
│   │   ├── context.py
│   │   ├── daily_pnl_reset_scheduler.py
│   │   ├── extended_order_service.py
│   │   ├── factory.py
│   │   ├── oms_gateway_proxy.py
│   │   ├── order_audit_logger.py
│   │   ├── order_manager.py
│   │   ├── order_position_updater.py
│   │   ├── order_repository_adapter.py
│   │   ├── order_state_validator.py
│   │   ├── portfolio_tracker.py
│   │   ├── position_manager.py
│   │   ├── position_repository_adapter.py
│   │   ├── protocols.py
│   │   ├── reconciliation_service.py
│   │   ├── risk_manager.py
│   │   ├── square_off_service.py
│   │   ├── _internal/
│   │   │   ├── __init__.py
│   │   │   ├── loss_circuit_breaker.py
│   │   │   ├── order_audit_logger.py
│   │   │   ├── order_position_updater.py
│   │   │   ├── order_state_validator.py
│   │   │   ├── reentrancy_guard.py
│   │   │   └── risk_manager.py
│   │   ├── persistence/
│   │   │   ├── __init__.py
│   │   │   └── sqlite_order_store.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_concurrent_rapid_fills.py
│   │       ├── test_correlation_id_warning.py
│   │       ├── test_graceful_shutdown.py
│   │       ├── test_loss_circuit_breaker.py
│   │       ├── test_oms.py
│   │       ├── test_oms_e2e.py
│   │       ├── test_oms_gateway_enforcement.py
│   │       ├── test_oms_writer_lock.py
│   │       ├── test_order_audit_logger.py
│   │       ├── test_order_position_updater.py
│   │       ├── test_order_state_validator.py
│   │       ├── test_partial_fill_lifecycle.py
│   │       ├── test_position_state_machine_enforcement.py
│   │       ├── test_reconciliation_gate.py
│   │       ├── test_reconciliation_service.py
│   │       ├── test_risk_manager_concurrency.py
│   │       ├── test_risk_manager_margin.py
│   │       ├── test_sqlite_order_store_restart.py
│   │       └── test_trade_idempotency.py
│   ├── portfolio/
│   │   ├── portfolio_service.py
│   │   └── tests/
│   │       └── test_portfolio_service.py
│   ├── scanner/
│   │   ├── scanner_service.py
│   │   └── tests/
│   │       └── test_scanner_service.py
│   └── trading/
│       ├── __init__.py
│       ├── feature_fetcher.py
│       ├── models.py
│       ├── multi_strategy_runtime.py
│       ├── trading_orchestrator.py
│       └── tests/
│           ├── test_multi_strategy_runtime.py
│           └── test_trading_orchestrator_e2e.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── async_event_bus.py
│   ├── cache.py
│   ├── correlation.py
│   ├── event_log.py
│   ├── global_exception_handler.py
│   ├── health.py
│   ├── logging_config.py
│   ├── retry.py
│   ├── state_machine.py
│   ├── time_service.py
│   ├── tracing.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── duckdb_pool.py
│   ├── event_bus/
│   │   ├── __init__.py
│   │   ├── dead_letter_queue.py
│   │   ├── event_bus.py
│   │   ├── factory.py
│   │   ├── persistent_dead_letter_queue.py
│   │   ├── processed_trade_repository.py
│   │   └── tests/
│   │       ├── test_async_event_bus_factory.py
│   │       ├── test_async_event_bus_priority.py
│   │       ├── test_persistent_dead_letter_queue.py
│   │       └── test_processed_trade_crash_recovery.py
│   ├── lifecycle/
│   │   ├── __init__.py
│   │   └── lifecycle.py
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── prometheus.py
│   │   ├── registry.py
│   │   └── types.py
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── alerting.py
│   │   ├── event_metrics.py
│   │   ├── http_server.py
│   │   └── tests/
│   │       ├── test_alerting.py
│   │       └── test_http_server.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── secret_manager.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       └── test_secret_manager.py
│   └── tests/
│       ├── __init__.py
│       ├── test_correlation_async.py
│       ├── test_duckdb_pool.py
│       ├── test_event_bus_lock_sharding.py
│       ├── test_global_exception_handler.py
│       ├── test_infrastructure_smoke.py
│       └── test_time_service.py
│
├── brokers/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── async_compat.py
│   │   ├── batch_executor.py
│   │   ├── batch_mixin.py
│   │   ├── bootstrap.py
│   │   ├── broker_port.py
│   │   ├── capabilities.py
│   │   ├── connection_pool.py
│   │   ├── dtos.py
│   │   ├── env_loader.py
│   │   ├── errors.py
│   │   ├── factory.py
│   │   ├── gateway.py
│   │   ├── gateway_errors.py
│   │   ├── gateway_interfaces.py
│   │   ├── historical_coordinator.py
│   │   ├── infrastructure.py
│   │   ├── instrument_adapter.py
│   │   ├── instruments.py
│   │   ├── intelligent_market_gateway.py
│   │   ├── models.py
│   │   ├── policy.py
│   │   ├── policy_defaults.py
│   │   ├── provenance.py
│   │   ├── quota_decorator.py
│   │   ├── quota_scheduler.py
│   │   ├── registry.py
│   │   ├── router.py
│   │   ├── settings.py
│   │   ├── ssl_hardening.py
│   │   ├── stream_orchestrator.py
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── extensions.py
│   │   │   ├── historical_mapper.py
│   │   │   └── market_data_gateway_adapter.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── spi.py
│   │   │   └── tests/
│   │   │       ├── __init__.py
│   │   │       └── run.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── credential_resolver.py
│   │   │   ├── credential_validator.py
│   │   │   ├── env_token.py
│   │   │   ├── environment_bootstrap.py
│   │   │   ├── jwt_expiry.py
│   │   │   ├── registry.py
│   │   │   ├── token.py
│   │   │   ├── token_persistence.py
│   │   │   ├── token_policy.py
│   │   │   ├── totp_cooldown.py
│   │   │   └── tests/
│   │   │       ├── test_credential_resolver.py
│   │   │       ├── test_credential_validator_upstox_files.py
│   │   │       ├── test_environment_bootstrap.py
│   │   │       ├── test_token_policy.py
│   │   │       └── test_totp_cooldown.py
│   │   ├── connection/
│   │   │   ├── authenticated_readiness.py
│   │   │   ├── bootstrap_result.py
│   │   │   ├── errors.py
│   │   │   ├── websocket_auth_coordinator.py
│   │   │   └── tests/
│   │   │       ├── test_authenticated_readiness.py
│   │   │       └── test_websocket_auth_coordinator.py
│   │   ├── contracts/
│   │   │   ├── __init__.py
│   │   │   ├── broker_contract.py
│   │   │   └── module_test_suite.py
│   │   ├── extensions/
│   │   │   ├── __init__.py
│   │   │   ├── deep_depth.py
│   │   │   ├── edis.py
│   │   │   ├── expired_options_history.py
│   │   │   ├── forever_order.py
│   │   │   ├── fundamentals.py
│   │   │   ├── market_intelligence.py
│   │   │   ├── native_slice_order.py
│   │   │   ├── news.py
│   │   │   ├── option_greeks_stream.py
│   │   │   └── super_order.py
│   │   ├── observability/
│   │   │   ├── __init__.py
│   │   │   ├── alerting.py
│   │   │   ├── audit.py
│   │   │   ├── event_metrics.py
│   │   │   ├── health_check.py
│   │   │   ├── http_server.py
│   │   │   └── tests/
│   │   │       ├── __init__.py
│   │   │       ├── test_alerting.py
│   │   │       └── test_http_observability_server.py
│   │   ├── oms/
│   │   │   ├── __init__.py
│   │   │   ├── RECOVERY.md
│   │   │   ├── margin_provider.py
│   │   │   └── tests/
│   │   │       ├── __init__.py
│   │   │       ├── test_concurrent_rapid_fills.py
│   │   │       ├── test_correlation_id_warning.py
│   │   │       ├── test_oms.py
│   │   │       ├── test_oms_e2e.py
│   │   │       ├── test_order_audit_logger.py
│   │   │       ├── test_order_position_updater.py
│   │   │       ├── test_order_state_validator.py
│   │   │       ├── test_partial_fill_lifecycle.py
│   │   │       ├── test_reconciliation_service.py
│   │   │       ├── test_risk_manager_concurrency.py
│   │   │       └── test_trade_idempotency.py
│   │   ├── options/
│   │   │   ├── __init__.py
│   │   │   ├── chain_normalizer.py
│   │   │   ├── gateway_facade.py
│   │   │   └── tests/
│   │   │       ├── __init__.py
│   │   │       └── test_chain_normalizer.py
│   │   ├── reconciliation/
│   │   │   ├── __init__.py
│   │   │   └── engine.py
│   │   ├── resilience/
│   │   │   ├── __init__.py
│   │   │   ├── backoff.py
│   │   │   ├── broker_health_monitor.py
│   │   │   ├── circuit_breaker.py
│   │   │   ├── error_codes.py
│   │   │   ├── errors.py
│   │   │   ├── rate_limiter.py
│   │   │   ├── retry.py
│   │   │   ├── retry_async.py
│   │   │   └── tests/
│   │   │       ├── __init__.py
│   │   │       ├── run.py
│   │   │       ├── test_backoff.py
│   │   │       ├── test_broker_health_monitor.py
│   │   │       ├── test_circuit_breaker.py
│   │   │       ├── test_endpoint_rate_limiter.py
│   │   │       ├── test_multi_bucket_rate_limiter.py
│   │   │       ├── test_retry.py
│   │   │       ├── test_retry_async.py
│   │   │       └── test_token_bucket_rate_limiter.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── benchmark.py
│   │   │   ├── data_validator.py
│   │   │   ├── download_engine.py
│   │   │   ├── historical_data.py
│   │   │   ├── instrument_registry.py
│   │   │   ├── production_readiness.py
│   │   │   └── tests/
│   │   │       └── test_production_readiness_fail_closed.py
│   │   └── tests/
│   │       ├── certify_broker.py
│   │       ├── conftest.py
│   │       ├── test_async_compat.py
│   │       ├── test_audit.py
│   │       ├── test_capabilities.py
│   │       ├── test_e2e_order_lifecycle.py
│   │       ├── test_event_bus_legacy.py
│   │       ├── test_event_log.py
│   │       ├── test_extension_factory_registry.py
│   │       ├── test_extensions_registry.py
│   │       ├── test_gateway_contract_integration.py
│   │       ├── test_gateway_contract_suite.py
│   │       ├── test_gateway_errors.py
│   │       ├── test_gateway_issues_regression.py
│   │       ├── test_historical_coordinator.py
│   │       ├── test_infrastructure_e2e.py
│   │       ├── test_intelligent_market_gateway.py
│   │       ├── test_live_broker_infrastructure.py
│   │       ├── test_logging_redaction.py
│   │       ├── test_market_data_gateway_adapter.py
│   │       ├── test_provenance_ledger.py
│   │       ├── test_quota_scheduler.py
│   │       ├── test_quota_scheduler_integration.py
│   │       ├── test_registry_router.py
│   │       ├── test_router_policy_integration.py
│   │       ├── test_ssl_hardening.py
│   │       ├── test_stream_orchestrator.py
│   │       ├── test_tick_handling.py
│   │       ├── test_untested_event_types.py
│   │       └── fixtures/
│   │           └── in_memory_gateway.py
│   │
│   ├── dhan/
│   │   ├── __init__.py
│   │   ├── alerts.py
│   │   ├── common_extensions.py
│   │   ├── conditional_triggers.py
│   │   ├── connection.py
│   │   ├── constants.py
│   │   ├── depth_20.py
│   │   ├── depth_200.py
│   │   ├── depth_feed_base.py
│   │   ├── domain.py
│   │   ├── edis.py
│   │   ├── exceptions.py
│   │   ├── exit_all.py
│   │   ├── extended.py
│   │   ├── factory.py
│   │   ├── forever_orders.py
│   │   ├── futures.py
│   │   ├── gateway.py
│   │   ├── historical.py
│   │   ├── http_client.py
│   │   ├── identity.py
│   │   ├── instrument_adapter.py
│   │   ├── invariants.py
│   │   ├── ip_management.py
│   │   ├── ledger.py
│   │   ├── loader.py
│   │   ├── margin.py
│   │   ├── market_data.py
│   │   ├── metrics.py
│   │   ├── options.py
│   │   ├── orders.py
│   │   ├── portfolio.py
│   │   ├── reconciliation.py
│   │   ├── reconnecting_service.py
│   │   ├── resolver.py
│   │   ├── resolver_refresher.py
│   │   ├── secret_utils.py
│   │   ├── segments.py
│   │   ├── settings.py
│   │   ├── status_mapper.py
│   │   ├── super_orders.py
│   │   ├── symbol_validator.py
│   │   ├── token_manager.py
│   │   ├── token_scheduler.py
│   │   ├── totp_client.py
│   │   ├── user_profile.py
│   │   ├── resilience/
│   │   │   ├── __init__.py
│   │   │   ├── circuit_breaker.py
│   │   │   ├── rate_limiter.py
│   │   │   └── retry_executor.py
│   │   ├── websocket/
│   │   │   ├── __init__.py
│   │   │   ├── _helpers.py
│   │   │   ├── market_feed.py
│   │   │   ├── order_stream.py
│   │   │   └── polling_feed.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       ├── contract/
│   │       │   ├── __init__.py
│   │       │   └── test_broker_contract.py
│   │       ├── fixtures/
│   │       │   ├── depth_200_ask_packet.bin
│   │       │   ├── depth_200_packet.bin
│   │       │   ├── depth_20_ask_packet.bin
│   │       │   └── depth_20_packet.bin
│   │       ├── integration/
│   │       │   ├── __init__.py
│   │       │   ├── conftest.py
│   │       │   ├── test_endpoint_latency.py
│   │       │   ├── test_error_paths.py
│   │       │   ├── test_live_batch_market_data.py
│   │       │   ├── test_live_derivatives_chain.py
│   │       │   ├── test_live_instruments.py
│   │       │   ├── test_live_market_data_rest.py
│   │       │   ├── test_live_observability.py
│   │       │   ├── test_live_options.py
│   │       │   ├── test_live_order_lifecycle.py
│   │       │   ├── test_live_portfolio.py
│   │       │   ├── test_live_quotes.py
│   │       │   ├── test_live_streaming.py
│   │       │   ├── test_live_validation.py
│   │       │   ├── test_live_websocket.py
│   │       │   ├── test_regression_suite.py
│   │       │   ├── test_schema_enforcement.py
│   │       │   ├── test_symbol_mapping_live.py
│   │       │   └── test_ws_parity.py
│   │       ├── regression/
│   │       │   ├── __init__.py
│   │       │   ├── conftest.py
│   │       │   ├── manifest.py
│   │       │   ├── test_coverage_manifest.py
│   │       │   ├── test_e2e_smoke.py
│   │       │   └── test_recent_fixes.py
│   │       └── unit/
│   │           ├── __init__.py
│   │           ├── test_alerts_adapter.py
│   │           ├── test_architecture_regression.py
│   │           ├── test_cache_refresh.py
│   │           ├── test_chaos.py
│   │           ├── test_circuit_breaker_regression.py
│   │           ├── test_conditional_triggers.py
│   │           ├── test_connection.py
│   │           ├── test_depth_200_websocket.py
│   │           ├── test_depth_20_websocket.py
│   │           ├── test_depth_feeds.py
│   │           ├── test_domain.py
│   │           ├── test_edge_cases.py
│   │           ├── test_edis.py
│   │           ├── test_exit_all.py
│   │           ├── test_factory.py
│   │           ├── test_factory_auth.py
│   │           ├── test_factory_websocket_wiring.py
│   │           ├── test_forever_orders.py
│   │           ├── test_futures.py
│   │           ├── test_gateway.py
│   │           ├── test_get_order_optimization.py
│   │           ├── test_historical.py
│   │           ├── test_http_client.py
│   │           ├── test_http_client_circuit_breaker_split.py
│   │           ├── test_ip_management.py
│   │           ├── test_ledger.py
│   │           ├── test_loader_cache_path.py
│   │           ├── test_margin_adapter.py
│   │           ├── test_market_data.py
│   │           ├── test_options.py
│   │           ├── test_order_factory_dhan_resolver.py
│   │           ├── test_orders.py
│   │           ├── test_orders_idempotency.py
│   │           ├── test_portfolio.py
│   │           ├── test_publish_depth_strict.py
│   │           ├── test_publish_tick_strict.py
│   │           ├── test_real_websocket_payloads.py
│   │           ├── test_reconciliation.py
│   │           ├── test_reconnecting_service.py
│   │           ├── test_resolver.py
│   │           ├── test_segments.py
│   │           ├── test_settings.py
│   │           ├── test_super_orders.py
│   │           ├── test_symbol_mapping.py
│   │           ├── test_token_bootstrap_policy.py
│   │           ├── test_token_broadcast.py
│   │           ├── test_token_scheduler.py
│   │           ├── test_token_scheduler_lifecycle.py
│   │           ├── test_user_profile.py
│   │           ├── test_websocket.py
│   │           ├── test_websocket_managed_service.py
│   │           ├── test_websocket_reconnect_recovery.py
│   │           ├── test_websocket_reconnection.py
│   │           └── test_websocket_thread_safety.py
│   │
│   ├── upstox/
│   │   ├── .gitignore
│   │   ├── __init__.py
│   │   ├── broker.py
│   │   ├── common_extensions.py
│   │   ├── extended.py
│   │   ├── factory.py
│   │   ├── gateway.py
│   │   ├── instrument_adapter.py
│   │   ├── metrics.py
│   │   ├── status_mapper.py
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── historical_adapter.py
│   │   │   ├── portfolio_adapter.py
│   │   │   ├── stream_manager.py
│   │   │   └── tick_translator.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── context.py
│   │   │   ├── exceptions.py
│   │   │   ├── holders.py
│   │   │   ├── http.py
│   │   │   ├── json_token_state_store.py
│   │   │   ├── login.py
│   │   │   ├── oauth_client.py
│   │   │   ├── pkce.py
│   │   │   ├── redirect_server.py
│   │   │   ├── token_expiry.py
│   │   │   ├── token_manager.py
│   │   │   ├── totp_client.py
│   │   │   ├── totp_scheduler.py
│   │   │   └── urls.py
│   │   ├── capabilities/
│   │   │   ├── __init__.py
│   │   │   ├── instruments.py
│   │   │   ├── market_data.py
│   │   │   ├── orders.py
│   │   │   ├── portfolio.py
│   │   │   └── streaming.py
│   │   ├── config/
│   │   │   ├── upstox-live.properties.example
│   │   │   └── upstox-sandbox.properties.example
│   │   ├── fundamentals/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── instruments/
│   │   │   ├── __init__.py
│   │   │   ├── definition.py
│   │   │   ├── loader.py
│   │   │   ├── resolver.py
│   │   │   ├── search.py
│   │   │   └── segment_mapper.py
│   │   ├── ipo/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── kill_switch/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── mappers/
│   │   │   ├── __init__.py
│   │   │   ├── domain_mapper.py
│   │   │   └── price_parser.py
│   │   ├── market_data/
│   │   │   ├── __init__.py
│   │   │   ├── client_v2.py
│   │   │   ├── client_v3.py
│   │   │   ├── expired_options.py
│   │   │   ├── futures.py
│   │   │   ├── futures_adapter.py
│   │   │   ├── historical_v2.py
│   │   │   ├── historical_v3.py
│   │   │   ├── margin.py
│   │   │   ├── margin_adapter.py
│   │   │   ├── market_data_adapter.py
│   │   │   ├── market_status.py
│   │   │   ├── market_status_adapter.py
│   │   │   ├── options_adapter.py
│   │   │   ├── options_client.py
│   │   │   ├── portfolio_adapter.py
│   │   │   ├── portfolio_client.py
│   │   │   └── trade_pnl.py
│   │   ├── market_intelligence/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   ├── client.py
│   │   │   └── snapshot.py
│   │   ├── mutual_funds/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── news/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── orders/
│   │   │   ├── __init__.py
│   │   │   ├── alert_adapter.py
│   │   │   ├── cover_order_adapter.py
│   │   │   ├── exit_all_adapter.py
│   │   │   ├── gtt_adapter.py
│   │   │   ├── gtt_client.py
│   │   │   ├── idempotency.py
│   │   │   ├── order_client.py
│   │   │   ├── order_command_adapter.py
│   │   │   ├── order_query_adapter.py
│   │   │   └── slice_adapter.py
│   │   ├── payments/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── reconciliation/
│   │   │   ├── __init__.py
│   │   │   └── service.py
│   │   ├── static_ip/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py
│   │   │   └── client.py
│   │   ├── websocket/
│   │   │   ├── __init__.py
│   │   │   ├── feed_authorizer.py
│   │   │   ├── lifecycle_wrapper.py
│   │   │   ├── market_data_v3.py
│   │   │   ├── portfolio_stream.py
│   │   │   ├── v3_auto_reconnect.py
│   │   │   ├── v3_decoder.py
│   │   │   ├── v3_subscription_manager.py
│   │   │   └── proto/
│   │   │       ├── MarketDataFeed.proto
│   │   │       ├── __init__.py
│   │   │       └── market_feed_pb2.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       ├── rate_limiter.py
│   │       ├── conformance/
│   │       │   └── fixtures/
│   │       │       ├── cancel-order-response.json
│   │       │       ├── feed-authorize-response.json
│   │       │       ├── historical-daily-response.json
│   │       │       ├── market-quote-response.json
│   │       │       ├── place-order-response.json
│   │       │       ├── token-refresh-response.json
│   │       │       └── token-response.json
│   │       ├── contract/
│   │       │   ├── __init__.py
│   │       │   ├── test_broker_contract.py
│   │       │   └── test_upstox_contract.py
│   │       ├── integration/
│   │       │   ├── conftest.py
│   │       │   ├── test_endpoint_latency.py
│   │       │   ├── test_error_paths.py
│   │       │   ├── test_live_batch_market_data.py
│   │       │   ├── test_live_derivatives_chain.py
│   │       │   ├── test_live_extended.py
│   │       │   ├── test_live_instruments.py
│   │       │   ├── test_live_market_data_rest.py
│   │       │   ├── test_live_options.py
│   │       │   ├── test_live_order_lifecycle.py
│   │       │   ├── test_live_portfolio.py
│   │       │   ├── test_live_quotes.py
│   │       │   ├── test_regression_suite.py
│   │       │   └── test_schema_enforcement.py
│   │       └── unit/
│   │           ├── __init__.py
│   │           ├── test_adapter_failures.py
│   │           ├── test_adapters_tick_translator.py
│   │           ├── test_architecture_regression.py
│   │           ├── test_broker_bundle_split.py
│   │           ├── test_capabilities_wiring.py
│   │           ├── test_context.py
│   │           ├── test_domain_mapper.py
│   │           ├── test_exceptions.py
│   │           ├── test_extended_lazy_load.py
│   │           ├── test_factory_totp_scheduler.py
│   │           ├── test_gateway_order_placement.py
│   │           ├── test_gateway_stream.py
│   │           ├── test_get_order_optimization.py
│   │           ├── test_gtt_adapter.py
│   │           ├── test_holders.py
│   │           ├── test_http_client.py
│   │           ├── test_instrument_loader.py
│   │           ├── test_jwt_expiry.py
│   │           ├── test_loader_pickle_security.py
│   │           ├── test_login.py
│   │           ├── test_new_features.py
│   │           ├── test_news.py
│   │           ├── test_oauth_client.py
│   │           ├── test_order_command_adapter.py
│   │           ├── test_order_query_adapter.py
│   │           ├── test_pkce.py
│   │           ├── test_price_parser.py
│   │           ├── test_redirect_server.py
│   │           ├── test_regression_fixes.py
│   │           ├── test_segment_mapper.py
│   │           ├── test_settings_loader.py
│   │           ├── test_token_expiry.py
│   │           ├── test_token_manager.py
│   │           ├── test_totp_bootstrap.py
│   │           ├── test_totp_client.py
│   │           ├── test_totp_scheduler.py
│   │           ├── test_trade_pnl.py
│   │           ├── test_upstox_resolver.py
│   │           ├── test_url_resolver.py
│   │           ├── test_websocket_lifecycle.py
│   │           ├── test_websocket_reconnect_recovery.py
│   │           └── test_websocket_safety.py
│   │
│   └── paper/
│       ├── __init__.py
│       ├── mock_broker.py
│       ├── paper_gateway.py
│       ├── paper_market_data.py
│       ├── paper_orders.py
│       ├── paper_portfolio.py
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py
│           ├── test_paper.py
│           ├── test_paper_orders_concurrency.py
│           └── contract/
│               └── test_paper_contract.py
│
├── api/
│   ├── __init__.py
│   ├── auth.py
│   ├── config.py
│   ├── deps.py
│   ├── freshness.py
│   ├── lifecycle.py
│   ├── main.py
│   ├── middleware.py
│   ├── schemas.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── analytics.py
│   │   ├── backtest.py
│   │   ├── health.py
│   │   ├── market.py
│   │   ├── news.py
│   │   ├── options.py
│   │   ├── orders.py
│   │   ├── portfolio.py
│   │   ├── replay.py
│   │   ├── risk.py
│   │   ├── scanner.py
│   │   ├── strategy.py
│   │   ├── symbols.py
│   │   └── live/
│   │       ├── __init__.py
│   │       ├── derivatives.py
│   │       ├── extended.py
│   │       ├── headers.py
│   │       ├── health.py
│   │       ├── market.py
│   │       ├── orders.py
│   │       ├── portfolio.py
│   │       ├── router.py
│   │       └── serialize.py
│   └── ws/
│       ├── __init__.py
│       ├── bridge.py
│       ├── feed_wiring.py
│       ├── market.py
│       └── replay.py
│
├── cli/
│   ├── composer_helpers.py
│   ├── main.py
│   ├── commands/
│   │   ├── account.py
│   │   ├── analytics.py
│   │   ├── analytics_backtest.py
│   │   ├── analytics_compare.py
│   │   ├── analytics_datalake.py
│   │   ├── analytics_halftrend.py
│   │   ├── analytics_optimize.py
│   │   ├── analytics_replay.py
│   │   ├── analytics_research.py
│   │   ├── analytics_scanner.py
│   │   ├── analytics_sector.py
│   │   ├── analytics_stock.py
│   │   ├── analytics_strategies.py
│   │   ├── analytics_utils.py
│   │   ├── analytics_walkforward.py
│   │   ├── benchmark.py
│   │   ├── broker.py
│   │   ├── cache_management.py
│   │   ├── certify.py
│   │   ├── compare.py
│   │   ├── dashboard.py
│   │   ├── events.py
│   │   ├── extended_orders.py
│   │   ├── instrument.py
│   │   ├── instrument_info.py
│   │   ├── instruments.py
│   │   ├── journal.py
│   │   ├── load_test.py
│   │   ├── market.py
│   │   ├── market_handlers.py
│   │   ├── news.py
│   │   ├── oms.py
│   │   ├── options_sync.py
│   │   ├── order_composition.py
│   │   ├── order_placement.py
│   │   ├── portfolio.py
│   │   ├── protocol.py
│   │   ├── quality_report.py
│   │   ├── registry.py
│   │   ├── risk_controls.py
│   │   ├── search.py
│   │   ├── validate.py
│   │   ├── validate_history.py
│   │   ├── validate_option_chain.py
│   │   ├── views.py
│   │   ├── websocket.py
│   │   ├── doctor/
│   │   │   ├── __init__.py
│   │   │   ├── checks.py
│   │   │   ├── orchestrator.py
│   │   │   ├── renderer.py
│   │   │   └── strategies/
│   │   │       ├── __init__.py
│   │   │       ├── active_broker.py
│   │   │       ├── authenticated_readiness.py
│   │   │       ├── broker_registry.py
│   │   │       ├── gateway_creation.py
│   │   │       ├── http_observability.py
│   │   │       ├── instrument_catalog.py
│   │   │       ├── lifecycle.py
│   │   │       ├── market_data.py
│   │   │       ├── oms_risk_manager.py
│   │   │       ├── order_api.py
│   │   │       └── portfolio.py
│   │   ├── market_data/
│   │   │   └── __init__.py
│   │   └── orders/
│   │       └── __init__.py
│   ├── diagnostics/
│   │   └── doctor.py
│   ├── load_testing/
│   │   └── runner.py
│   ├── services/
│   │   ├── broker_lifecycle.py
│   │   ├── broker_observability.py
│   │   ├── broker_registry.py
│   │   ├── broker_service.py
│   │   ├── capital_provider.py
│   │   ├── compose.py
│   │   ├── event_bus_service.py
│   │   ├── observability_setup.py
│   │   ├── oms_service.py
│   │   ├── oms_setup.py
│   │   └── websocket_wiring.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── error_formatter.py
│   │   ├── retry_handler.py
│   │   └── timeout_handler.py
│   ├── views/
│   │   ├── tui.tcss
│   │   └── tui_app.py
│   ├── widgets/
│   │   ├── broker_console.py
│   │   ├── diagnostics_console.py
│   │   ├── event_ws_console.py
│   │   ├── market_console.py
│   │   ├── oms_console.py
│   │   └── performance_console.py
│   └── tests/
│       ├── conftest.py
│       ├── endpoint_manifest.py
│       ├── test_analytics_commands.py
│       ├── test_b7_oms_wireup.py
│       ├── test_broker_infrastructure.py
│       ├── test_broker_not_ready.py
│       ├── test_broker_registry.py
│       ├── test_broker_service_auth_readiness.py
│       ├── test_broker_service_concurrency.py
│       ├── test_broker_service_lifecycle.py
│       ├── test_cli_endpoint_matrix.py
│       ├── test_command_registry.py
│       ├── test_commands.py
│       ├── test_doctor_commands.py
│       ├── test_doctor_orchestrator.py
│       ├── test_doctor_renderer.py
│       ├── test_doctor_strategies.py
│       ├── test_extended_commands.py
│       ├── test_http_observability_wireup.py
│       ├── test_market_commands.py
│       ├── test_oms_modify.py
│       ├── test_oms_service.py
│       ├── test_oms_setup_persistence.py
│       ├── test_order_composition.py
│       ├── test_order_placement.py
│       ├── test_order_sandbox_integration.py
│       ├── test_portfolio_commands.py
│       ├── test_risk_controls.py
│       ├── test_timeout_retry_error.py
│       ├── test_tui.py
│       ├── test_validate_commands.py
│       ├── test_verbose_timing_flags.py
│       └── test_views_journal_commands.py
│
├── analytics/
│   ├── __init__.py
│   ├── precompute_features.py
│   ├── backtest/
│   │   ├── __init__.py
│   │   ├── comparator.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── optimizer.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_comparator.py
│   │       └── test_optimizer.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── feature_builder.py
│   │   ├── models.py
│   │   └── providers.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── relative_strength.py
│   │   └── volume.py
│   ├── futures/
│   │   ├── __init__.py
│   │   └── futures_analytics.py
│   ├── indicators/
│   │   ├── __init__.py
│   │   ├── halftrend.py
│   │   ├── halftrend_backtest.py
│   │   ├── market_structure.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_halftrend.py
│   │       └── test_swing_detection.py
│   ├── market_breadth/
│   │   ├── __init__.py
│   │   └── breadth.py
│   ├── options/
│   │   ├── __init__.py
│   │   └── options_analytics.py
│   ├── orderflow/
│   │   ├── __init__.py
│   │   └── orderflow.py
│   ├── paper/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   └── models.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── features.py
│   │   └── pipeline.py
│   ├── probability/
│   │   ├── __init__.py
│   │   └── probability.py
│   ├── ranking/
│   │   ├── __init__.py
│   │   ├── ranking.py
│   │   └── tests/
│   │       └── test_ranking_integration.py
│   ├── replay/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── golden_dataset.py
│   │   ├── models.py
│   │   ├── orchestrator.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_commission_model.py
│   │       ├── test_fill_model.py
│   │       ├── test_pnl_precision.py
│   │       ├── test_replay_memory.py
│   │       └── test_slippage_model.py
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── reports.py
│   │   └── tests/
│   │       └── test_reports_integration.py
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── runner.py
│   │   ├── scanner_queries.py
│   │   ├── scanners.py
│   │   ├── scorer.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_determinism.py
│   │       ├── test_scanner_performance.py
│   │       └── test_scanner_queries.py
│   ├── sector/
│   │   ├── __init__.py
│   │   ├── analyzer.py
│   │   ├── mapping.py
│   │   ├── rotation.py
│   │   ├── strength.py
│   │   └── volume.py
│   ├── stocks/
│   │   ├── __init__.py
│   │   ├── find_levels.py
│   │   ├── stock_analytics.py
│   │   └── tests/
│   │       └── test_find_levels.py
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── evaluator_bridge.py
│   │   ├── models.py
│   │   ├── pipeline.py
│   │   ├── protocols.py
│   │   ├── registry.py
│   │   └── builtins/
│   │       ├── __init__.py
│   │       └── halftrend.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── helpers.py
│   │   ├── test_backtest.py
│   │   ├── test_breadth.py
│   │   ├── test_core.py
│   │   ├── test_deep_dive.py
│   │   ├── test_features.py
│   │   ├── test_greeks.py
│   │   ├── test_indicators.py
│   │   ├── test_market_structure.py
│   │   ├── test_options.py
│   │   ├── test_orderflow.py
│   │   ├── test_paper.py
│   │   ├── test_pipeline.py
│   │   ├── test_providers.py
│   │   ├── test_ranking_determinism.py
│   │   ├── test_replay.py
│   │   ├── test_reports.py
│   │   ├── test_scanner.py
│   │   ├── test_sector.py
│   │   ├── test_stocks.py
│   │   ├── test_strategy.py
│   │   ├── test_visualizations.py
│   │   ├── test_volatility.py
│   │   └── test_volume_profile.py
│   ├── views/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── cache_manager.py
│   │   ├── features.py
│   │   ├── manager.py
│   │   ├── options_views.py
│   │   ├── quality.py
│   │   ├── query_executor.py
│   │   ├── scanner.py
│   │   ├── strategy.py
│   │   ├── validator.py
│   │   ├── view_registry.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_view_determinism.py
│   │       └── test_views.py
│   ├── visualizations/
│   │   ├── __init__.py
│   │   └── charts.py
│   ├── volatility/
│   │   ├── __init__.py
│   │   └── volatility_analytics.py
│   ├── volume_profile/
│   │   ├── __init__.py
│   │   └── volume_profile.py
│   └── walk_forward/
│       ├── __init__.py
│       ├── engine.py
│       └── tests/
│           └── test_walk_forward.py
│
├── datalake/
│   ├── __init__.py
│   ├── backtest_cache_store.py
│   ├── cache_utils.py
│   ├── catalog.py
│   ├── converter.py
│   ├── corporate_actions.py
│   ├── duckdb_utils.py
│   ├── fast_backtest.py
│   ├── features.py
│   ├── gateway.py
│   ├── health_check.py
│   ├── io.py
│   ├── journal.py
│   ├── loader.py
│   ├── migrations.py
│   ├── monitor.py
│   ├── normalize.py
│   ├── nse_calendar.py
│   ├── option_format.py
│   ├── options_analytics_sql.py
│   ├── options_greeks.py
│   ├── paths.py
│   ├── pit_joins.py
│   ├── quality.py
│   ├── quality_universe.py
│   ├── relative_volume.py
│   ├── research.py
│   ├── research_dataset.py
│   ├── run_backtest.py
│   ├── scan_store.py
│   ├── scanner_universe.py
│   ├── schema.py
│   ├── symbols.py
│   ├── sync_options.py
│   ├── universe.py
│   ├── updater.py
│   ├── validation.py
│   ├── views.py
│   ├── vwap.py
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── corporate_actions.py
│   │   ├── features.py
│   │   ├── options_analytics_sql.py
│   │   ├── options_greeks.py
│   │   ├── relative_volume.py
│   │   ├── support_resistance.py
│   │   └── vwap.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── duckdb_utils.py
│   │   ├── io.py
│   │   ├── migrations.py
│   │   ├── nse_calendar.py
│   │   ├── option_format.py
│   │   ├── paths.py
│   │   ├── pit_joins.py
│   │   ├── schema.py
│   │   ├── serialization.py
│   │   ├── symbols.py
│   │   └── universe.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── converter.py
│   │   ├── loader.py
│   │   ├── normalize.py
│   │   ├── sync_options.py
│   │   └── updater.py
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── resources.py
│   │   ├── server.py
│   │   └── tools.py
│   ├── quality/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── health_check.py
│   │   ├── monitor.py
│   │   ├── universe.py
│   │   └── validation.py
│   ├── research/
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── backtest_cache_store.py
│   │   ├── dataset.py
│   │   ├── fast_backtest.py
│   │   ├── journal.py
│   │   ├── run_backtest.py
│   │   ├── scan_store.py
│   │   └── scanner_universe.py
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── compiler.py
│   │   ├── engine.py
│   │   ├── models.py
│   │   └── rules/
│   │       ├── momentum_breakout.json
│   │       └── volume_spike.json
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── cache_utils.py
│   │   ├── catalog.py
│   │   ├── parquet_store.py
│   │   └── views.py
│   ├── store/
│   │   └── __init__.py
│   └── tests/
│       ├── __init__.py
│       ├── test_atomic_io.py
│       ├── test_catalog.py
│       ├── test_converter.py
│       ├── test_corporate_actions.py
│       ├── test_duckdb_e2e.py
│       ├── test_duckdb_pool_concurrency.py
│       ├── test_features.py
│       ├── test_fixes.py
│       ├── test_gateway_batch.py
│       ├── test_health_check.py
│       ├── test_integration.py
│       ├── test_journal.py
│       ├── test_migrations.py
│       ├── test_monitor.py
│       ├── test_normalize.py
│       ├── test_option_format.py
│       ├── test_options_analytics.py
│       ├── test_options_greeks.py
│       ├── test_parquet_store.py
│       ├── test_paths.py
│       ├── test_perf_ltp_quote.py
│       ├── test_pit_joins.py
│       ├── test_quality.py
│       ├── test_quality_universe.py
│       ├── test_research.py
│       ├── test_research_dataset.py
│       ├── test_retry.py
│       ├── test_scan_store.py
│       ├── test_schema.py
│       ├── test_support_resistance.py
│       ├── test_symbols.py
│       ├── test_update_env_token.py
│       ├── test_validation.py
│       └── test_vwap.py
│
├── runtime/
│   ├── __init__.py
│   ├── api_bootstrap.py
│   ├── broker_runtime.py
│   ├── composition.py
│   ├── parity_gate.py
│   ├── production_config.py
│   └── trading_runtime_factory.py
│
├── frontend/
│   ├── README.md
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── vite-env.d.ts
│       ├── api/
│       │   └── client.ts
│       ├── components/
│       │   ├── CandlestickChart.tsx
│       │   ├── ChartPanel.tsx
│       │   ├── ChartToolbar.tsx
│       │   ├── CommandBar.tsx
│       │   ├── FunctionKeyBar.tsx
│       │   ├── MarketDepth.tsx
│       │   ├── NewsTicker.tsx
│       │   ├── ReplayPanel.tsx
│       │   ├── Sidebar.tsx
│       │   ├── SymbolSearch.tsx
│       │   ├── TimeAndSales.tsx
│       │   └── TopBar.tsx
│       ├── data/
│       │   ├── mockMarket.ts
│       │   ├── orderflow.ts
│       │   └── symbols.ts
│       ├── hooks/
│       │   ├── useCandles.ts
│       │   ├── useMarketDepth.ts
│       │   ├── useMarketStream.ts
│       │   ├── useNews.ts
│       │   ├── useQuote.ts
│       │   └── useTrades.ts
│       ├── lib/
│       │   └── utils.ts
│       ├── store/
│       │   └── app.ts
│       ├── styles/
│       │   └── globals.css
│       ├── types/
│       │   └── index.ts
│       └── __tests__/
│           ├── App.test.tsx
│           ├── TopBar.test.tsx
│           ├── setup.ts
│           ├── store.test.ts
│           └── useMarketStream.test.ts
│
├── scripts/
│   ├── PARALLEL_EXECUTION_MONITOR.sh
│   ├── VERIFICATION_REPORT.md
│   ├── audit_broker_methods.py
│   ├── baseline_quant_parity.py
│   ├── benchmark_multi_symbol_speed.py
│   ├── capability_report.py
│   ├── check_constants_placement.py
│   ├── check_data_freshness.py
│   ├── check_data_quality.py
│   ├── clean_indices.py
│   ├── cleanup_unused_imports.py
│   ├── detect_flaky_tests.py
│   ├── dhan_regression_report.py
│   ├── generate_dependency_graph.py
│   ├── generate_depth_golden_packets.py
│   ├── migrate_shim_imports.py
│   ├── production_certification.py
│   ├── refresh_stale_symbols.py
│   ├── revalidate_upstox_known_issues.py
│   ├── run_broker_tests.sh
│   ├── run_mutation_tests.sh
│   ├── test_depth_websocket.py
│   ├── test_dhan_all_modes.py
│   ├── test_live_depth.py
│   ├── test_regression_mapping.py
│   ├── test_totp_flow.py
│   ├── validate_totp_setup.py
│   ├── verify_all.py
│   ├── verify_dhan_endpoints.py
│   ├── verify_event_replay.py
│   ├── verify_live_feed_depth.py
│   ├── verify_nse_mcx_segments.py
│   ├── verify_upstox_news.py
│   ├── with_venv.sh
│   ├── architecture/
│   │   └── check_exception_hierarchy.py
│   └── migration/
│       ├── __init__.py
│       ├── migrate_to_curated_layout.py
│       └── seed_universe_history.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── market_hours.py
│   ├── run.py
│   ├── test_architecture.py
│   ├── test_benchmark.py
│   ├── test_broker_router.py
│   ├── test_buffered_event_log.py
│   ├── test_connection_pool.py
│   ├── test_data_validator.py
│   ├── test_domain_event_immutability.py
│   ├── test_download_engine.py
│   ├── test_identity.py
│   ├── test_identity_coercion.py
│   ├── test_instrument_adapters.py
│   ├── test_instrument_id.py
│   ├── test_instrument_integration.py
│   ├── test_instrument_registry.py
│   ├── test_instrument_resolver.py
│   ├── test_invariants.py
│   ├── test_md5_cache_disable.py
│   ├── test_portfolio_tracker.py
│   ├── test_replay_orchestrator.py
│   ├── test_scanner_runner.py
│   ├── test_security_findings.py
│   ├── test_sql_injection.py
│   ├── test_token_expiry_validation.py
│   ├── api/
│   │   ├── conftest.py
│   │   ├── test_analytics_endpoints.py
│   │   ├── test_auth.py
│   │   ├── test_auth_default_mode.py
│   │   ├── test_backtest_comparison.py
│   │   ├── test_backtest_endpoints.py
│   │   ├── test_cache_headers.py
│   │   ├── test_extended_order_routes.py
│   │   ├── test_freshness.py
│   │   ├── test_health.py
│   │   ├── test_health_symbols.py
│   │   ├── test_live_doctor_parity.py
│   │   ├── test_live_extended_account.py
│   │   ├── test_live_extended_orders.py
│   │   ├── test_live_health.py
│   │   ├── test_live_market_endpoints.py
│   │   ├── test_market_analytics.py
│   │   ├── test_market_endpoints.py
│   │   ├── test_oms_lifecycle.py
│   │   ├── test_options_bid_ask.py
│   │   ├── test_options_replay.py
│   │   ├── test_order_endpoints.py
│   │   ├── test_order_validation.py
│   │   ├── test_performance.py
│   │   ├── test_portfolio_endpoints.py
│   │   ├── test_portfolio_integration.py
│   │   ├── test_portfolio_orders.py
│   │   ├── test_rate_limit.py
│   │   ├── test_replay_endpoints.py
│   │   ├── test_scanner_endpoints.py
│   │   ├── test_scanner_run.py
│   │   ├── test_service_container.py
│   │   ├── test_square_off.py
│   │   ├── test_vectorized_candles.py
│   │   ├── test_ws_market.py
│   │   └── test_ws_replay.py
│   ├── architecture/
│   │   ├── __init__.py
│   │   ├── test_architecture_fitness.py
│   │   ├── test_cross_cutting_concerns.py
│   │   ├── test_deepening_enforcement.py
│   │   ├── test_domain_isolation.py
│   │   ├── test_domain_single_source.py
│   │   ├── test_gateway_abc_compliance.py
│   │   ├── test_gateway_signatures.py
│   │   ├── test_no_duplicate_error_hierarchies.py
│   │   └── test_no_scattered_dotenv.py
│   ├── capability/
│   │   ├── __init__.py
│   │   ├── test_api_route_manifest.py
│   │   ├── test_audit_broker_methods.py
│   │   ├── test_capability_manifest_contract.py
│   │   ├── test_cli_gateway_calls.py
│   │   ├── test_cli_rest_parity.py
│   │   ├── test_extended_capabilities_registered.py
│   │   ├── test_gateway_abc_compliance.py
│   │   └── test_rest_data_source_contract.py
│   ├── chaos/
│   │   ├── __init__.py
│   │   ├── test_broker_disconnect.py
│   │   ├── test_cleanup_phantom_dirs.py
│   │   ├── test_concurrent_failures.py
│   │   ├── test_data_corruption.py
│   │   ├── test_dlq_scenarios.py
│   │   ├── test_event_bus_replay_api.py
│   │   ├── test_failover.py
│   │   ├── test_failure_modes.py
│   │   ├── test_network_partitions.py
│   │   ├── test_rate_limit_exhaustion.py
│   │   ├── test_reconciliation_failures.py
│   │   └── test_recovery_certification.py
│   ├── contract/
│   │   ├── test_broker_gateway_contract.py
│   │   └── test_protocol_implementations.py
│   ├── e2e/
│   │   ├── __init__.py
│   │   ├── test_circuit_breaker_recovery_flow.py
│   │   ├── test_cli_real_data.py
│   │   ├── test_complete_trading_flow.py
│   │   ├── test_initialization_flow.py
│   │   ├── test_lock_contention.py
│   │   ├── test_market_data_to_order_flow.py
│   │   ├── test_order_lifecycle.py
│   │   ├── test_replay_backtest_flow.py
│   │   ├── test_resource_leaks.py
│   │   ├── test_sandbox_real_broker.py
│   │   ├── test_scanner_to_order_flow.py
│   │   ├── test_signal_to_reconciliation_flow.py
│   │   ├── test_token_refresh_and_order_retry_flow.py
│   │   ├── test_trading_flow.py
│   │   ├── test_websocket_to_pnl_flow.py
│   │   └── fixtures/
│   │       ├── __init__.py
│   │       ├── data_generators.py
│   │       ├── event_capturer.py
│   │       ├── mock_brokers.py
│   │       └── trading_context_factory.py
│   ├── fakes/
│   │   ├── __init__.py
│   │   ├── fake_oms.py
│   │   └── fake_trading.py
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── domain_helpers.py
│   │   ├── fake_broker_gateway.py
│   │   ├── market_symbols.py
│   │   └── test_fake_broker_gateway.py
│   ├── integration/
│   │   ├── auth_gates.py
│   │   ├── test_auth_failure_paths.py
│   │   ├── test_auth_totp_live.py
│   │   ├── test_cancel_verification.py
│   │   ├── test_cli_to_application_chain.py
│   │   ├── test_config_validation_integration.py
│   │   ├── test_cross_broker_parity.py
│   │   ├── test_dhan_api_live_readonly.py
│   │   ├── test_event_bus_flow.py
│   │   ├── test_event_log_replay.py
│   │   ├── test_event_replay_determinism.py
│   │   ├── test_execution_parity.py
│   │   ├── test_gateway_contract.py
│   │   ├── test_kill_switch_atomic_flip.py
│   │   ├── test_oms_broker_integration.py
│   │   ├── test_processed_trade_repository_crash_recovery.py
│   │   ├── test_resilience_composition.py
│   │   ├── test_restart_trade_replay.py
│   │   ├── test_runtime_validation_audit.py
│   │   ├── test_trading_runtime_orchestrator.py
│   │   ├── test_upstox_gateway_integration.py
│   │   ├── test_upstox_market_data.py
│   │   ├── test_upstox_order_lifecycle.py
│   │   ├── test_upstox_portfolio_oms.py
│   │   ├── test_view_manager_composition.py
│   │   ├── test_websocket_reconnect_failure.py
│   │   └── fixtures/
│   │       ├── __init__.py
│   │       ├── domain.py
│   │       ├── event_bus.py
│   │       └── upstox.py
│   ├── oms/
│   │   ├── test_order_state_transitions.py
│   │   └── test_processed_trade_repository_singleton.py
│   ├── performance/
│   │   ├── __init__.py
│   │   ├── test_benchmarks.py
│   │   ├── test_data_performance.py
│   │   └── test_performance.py
│   ├── property/
│   │   ├── test_domain_properties.py
│   │   ├── test_market_data_properties.py
│   │   ├── test_order_properties.py
│   │   └── test_property_based.py
│   ├── quant/
│   │   ├── __init__.py
│   │   ├── baseline.py
│   │   ├── parity_config.py
│   │   ├── test_cross_broker_parity.py
│   │   ├── test_paper_replay_parity.py
│   │   ├── test_quant_parity.py
│   │   └── golden/
│   │       ├── feature_parity.json
│   │       ├── replay_pnl.json
│   │       ├── resample_correctness.json
│   │       └── scanner_determinism.json
│   ├── regression/
│   │   ├── test_golden_dataset.py
│   │   ├── test_memory_leaks.py
│   │   └── test_phase_1_6_refactoring.py
│   ├── runtime/
│   │   ├── test_production_config.py
│   │   └── test_trading_runtime_factory.py
│   ├── scripts/
│   │   ├── test_broker_connections.py
│   │   ├── test_cli_speed.py
│   │   ├── test_options_contracts.py
│   │   ├── test_options_gateway.py
│   │   └── test_upstox_historical_fix.py
│   ├── stability/
│   │   ├── test_event_bus_idempotency.py
│   │   ├── test_metrics.py
│   │   ├── test_structured_logging.py
│   │   ├── test_tracing.py
│   │   └── test_typed_events_and_idempotency.py
│   ├── stress/
│   │   └── test_oms_stress.py
│   └── unit/
│       ├── test_config_schema.py
│       └── test_domain_port_contracts.py
│
├── market_data/                    (runtime data — parquet, sqlite, duckdb)
│   ├── catalog.duckdb
│   ├── journal.sqlite
│   ├── oms_orders.sqlite
│   ├── live_snapshot.json
│   ├── equities/candles/timeframe=1m/
│   ├── indices/candles/timeframe=1m/symbol=NIFTY/
│   ├── materialized/
│   └── options/candles/
│
├── analytics_cache/
│   └── versions/
│       ├── m_duplicate_candles/
│       ├── m_intraday/
│       ├── m_intraday_snapshot/
│       ├── m_iv_surface/
│       ├── m_max_pain/
│       ├── m_missing_candles/
│       ├── m_pcr/
│       ├── m_recent_daily/
│       ├── m_symbol_snapshot/
│       └── m_trading_days/
│
├── runtime-dev/
│   └── instruments/
│       ├── api-scrip-master-*.csv
│       ├── instruments_*.csv
│       ├── complete_sample.json.gz
│       └── sample.json.gz
│
└── reports/
    └── ARCHITECTURE_AUDIT_REPORT.md
```

---

## 2. Architecture As-Is

### 2.1 Layered Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ENTRY POINTS                                                            │
│  api_server.py (FastAPI/uvicorn)  │  cli/main.py (Rich/TUI)             │
├──────────────────────────────────────────────────────────────────────────┤
│  API LAYER  (api/)                                                       │
│  FastAPI routers, WebSocket handlers, auth, middleware, schemas          │
├──────────────────────────────────────────────────────────────────────────┤
│  CLI/TUI LAYER  (cli/)                                                   │
│  Commands, services, widgets, TUI views, diagnostics (doctor)           │
├──────────────────────────────────────────────────────────────────────────┤
│  APPLICATION LAYER  (application/)                                       │
│  Use cases: execution/, oms/, composer/, trading/, scanner/,             │
│             portfolio/, backtest/                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  DOMAIN LAYER  (domain/)         ← SINGLE SOURCE OF TRUTH               │
│  Entities, value objects, enums, ports (protocols), constants,           │
│  events, repositories                                                    │
├──────────────────────────────────────────────────────────────────────────┤
│  BROKER LAYER  (brokers/)                                                │
│  common/ (broker-agnostic infra)  │  dhan/  │  upstox/  │  paper/       │
├──────────────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE LAYER  (infrastructure/)                                 │
│  event_bus/, lifecycle/, metrics/, observability/, security/,            │
│  db/, logging, retry, tracing, caching                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  ANALYTICS LAYER  (analytics/)                                           │
│  backtest, scanner, replay, strategy, sector, indicators,                │
│  options, orderflow, views, pipeline, walk_forward                       │
├──────────────────────────────────────────────────────────────────────────┤
│  DATALAKE LAYER  (datalake/)                                             │
│  DuckDB-backed storage, ingestion, quality, research, MCP server,        │
│  scanner engine, analytics SQL, parquet store                            │
├──────────────────────────────────────────────────────────────────────────┤
│  CONFIG  (config/)  │  RUNTIME  (runtime/)                               │
│  Profiles, validation,  Composition root, bootstrap,                     │
│  feature flags, secrets   parity gate, production config                │
├──────────────────────────────────────────────────────────────────────────┤
│  FRONTEND  (frontend/)                                                   │
│  React + TypeScript + Vite + Tailwind CSS SPA                           │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Responsibilities

| Layer | Package | Responsibility |
|---|---|---|
| **Domain** | `domain/` | Canonical types (entities, value objects, enums), ports (protocol interfaces), constants, events. **Zero external dependencies.** Single source of truth. |
| **Application** | `application/` | Use-case orchestration: OMS (`order_manager.py`, `context.py`, `risk_manager.py`), execution service, trading orchestrator, composer (multi-broker), scanner/portfolio/backtest services. |
| **Infrastructure** | `infrastructure/` | Cross-cutting concerns: event bus (async + dead-letter queue), lifecycle manager, DuckDB connection pool, observability (Prometheus, alerting, HTTP server), security (secret manager), logging, retry, tracing, state machine. |
| **Brokers** | `brokers/` | Broker adapter layer. `common/` holds broker-agnostic infrastructure (gateway, stream orchestrator, resilience, auth, OMS, reconciliation). `dhan/`, `upstox/`, `paper/` are broker-specific implementations. |
| **API** | `api/` | FastAPI application factory. REST routers for health, symbols, market, analytics, scanner, strategy, options, replay, backtest, portfolio, orders, risk, news, live broker. WebSocket for market data and replay. |
| **CLI** | `cli/` | Rich/TUI command-line interface. Commands for broker management, market data, orders, OMS, analytics, diagnostics (doctor), plus TUI widgets and views. |
| **Analytics** | `analytics/` | Quantitative analytics: backtest engine/optimizer/comparator, scanner, replay engine, strategy pipeline, sector rotation, indicators (HalfTrend, market structure), options analytics, orderflow, volume profile, volatility, walk-forward. |
| **Datalake** | `datalake/` | DuckDB-backed data lake: ingestion, storage (parquet), catalog, quality monitoring, research/backtest, MCP server, scanner engine, analytics SQL views. |
| **Config** | `config/` | Configuration schema, validation, feature flags, environment profiles (dev/staging/prod), secrets management, endpoint/index definitions. |
| **Runtime** | `runtime/` | Composition root. `TradingRuntimeFactory` wires broker gateways, OMS, orchestrator, event bus, and observability into a `Runtime` dataclass. `api_bootstrap.py` initializes services for the API process. |
| **Frontend** | `frontend/` | React + TypeScript + Vite + Tailwind CSS SPA. Components: CandlestickChart, MarketDepth, TimeAndSales, ReplayPanel, CommandBar, SymbolSearch, etc. WebSocket hooks for live market streaming. |

### 2.3 Module Dependency Rules (Import-Linter Contracts)

Enforced via `.import-linter.ini` and `pyproject.toml`:

| Contract | Source Module | Forbidden Imports | Rationale |
|---|---|---|---|
| **Domain independence** | `domain` | `brokers`, `analytics`, `datalake`, `cli`, `application`, `api` | Domain is the leaf layer — no outward dependencies |
| **Infrastructure independence** | `infrastructure` | `brokers`, `analytics`, `cli`, `application`, `api` | Infrastructure must be layer-independent |
| **Application broker isolation** | `application` | `brokers.dhan`, `brokers.upstox`, `brokers.paper` | Application uses ports, not implementations |
| **Broker common isolation** | `brokers.common` | `brokers.dhan`, `brokers.upstox`, `analytics` | Common code doesn't know about specific brokers |
| **Cross-broker isolation (D↔U)** | `brokers.dhan` ↔ `brokers.upstox` | Each other | Cross-broker imports are design errors |
| **Analytics broker-adapter isolation** | `analytics` | `brokers.dhan`, `brokers.upstox`, `brokers.paper`, `cli` | Analytics is broker-agnostic |
| **No CLI in datalake/analytics** | `datalake`, `analytics` | `cli` | Lower layers cannot import CLI |
| **API-CLI separation** | `api` | `cli` | API server can't import CLI |

### 2.4 Dependency Direction Summary (Allowed →)

```
domain           →  (nothing — leaf layer, zero outward deps)
infrastructure   →  domain
application      →  domain, infrastructure
brokers.common   →  domain, infrastructure
brokers.{x}      →  domain, infrastructure, brokers.common
analytics        →  domain, infrastructure, datalake
datalake         →  domain, infrastructure
api              →  domain, application, infrastructure, analytics, datalake, brokers, config, runtime
cli              →  everything (top-level consumer)
runtime          →  brokers.common, infrastructure, application, config, datalake, analytics
```

### 2.5 Key Entry Points

| Entry Point | File | Purpose |
|---|---|---|
| `api_server.py` | Root | FastAPI/uvicorn server bootstrap |
| `cli/main.py` | `cli/` | Rich/TUI command-line interface |
| `TradingRuntimeFactory` | `runtime/trading_runtime_factory.py` | Single composition root shared by CLI, API, and scripts |
| `create_app()` | `api/main.py` | FastAPI application factory |
| `initialize_api_services()` | `runtime/api_bootstrap.py` | Wires DataLake, ViewManager, TradingRuntime for API |



---

## 3. Application Flows

### 3.1 API Bootstrap Flow

```
api_server.py (entry point)
  │
  ├── configure_logging()                         # infrastructure/logging_config.py
  ├── bootstrap_environment(project_root)          # brokers/common/auth/environment_bootstrap.py
  ├── initialize_api_services(project_root)        # runtime/api_bootstrap.py
  │     │
  │     ├── DataLakeGateway(root=...)              # datalake/gateway.py
  │     ├── DataCatalog(root=...)                  # datalake/catalog.py
  │     ├── ViewManager(catalog_path=...)          # analytics/views/manager.py
  │     │
  │     └── TradingRuntimeFactory.build_for_api()  # runtime/trading_runtime_factory.py
  │           │
  │           ├── create_api_event_bus()           # runtime/composition.py
  │           ├── BrokerService(event_bus=...)     # cli/services/broker_service.py
  │           ├── validate_production_config()     # runtime/production_config.py
  │           ├── assert_runtime_parity_or_raise() # runtime/parity_gate.py
  │           ├── Wire gateway (Dhan/Upstox)
  │           ├── Wire TradingContext (OMS)
  │           ├── Wire TradingOrchestrator
  │           └── Wire BrokerInfrastructure (multi-broker)
  │
  └── create_app(config=..., **services)           # api/main.py
        │
        ├── validate_production_config(surface="api")
        ├── Register domain runtime hooks
        ├── initialize_all_services() → DI container
        ├── FastAPI app creation
        ├── Add middleware (RequestLogging, RateLimit, CORS)
        ├── setup_exception_handlers()
        └── Include 16 routers + 2 WebSocket routers
              /api/v1/health, /symbols, /market, /analytics,
              /scanner, /strategy, /options, /replay, /backtest,
              /portfolio, /orders, /risk, /news, /live/*
              /ws/market, /ws/replay
```

### 3.2 API Lifespan (Startup / Shutdown)

```
lifespan(app)                                        # api/lifecycle.py
  ├── get_container() → DI container
  ├── ctx = container.trading_context
  ├── LifecycleManager() → start_all()
  │     (reconciliation, DLQ monitor, daily PnL reset)
  ├── MarketBridge(event_bus, connection_manager) → start()
  │     (bridges EventBus ticks → WebSocket clients)
  │
  ├── [on shutdown]
  │     ├── MarketBridge.stop()
  │     ├── LifecycleManager.stop_all()
  │     └── close_all_connections() (DuckDB)
```

### 3.3 CLI Entry Flow

```
cli/main.py
  │
  ├── TradingRuntimeFactory(broker=..., ...)
  │     └── build() → Runtime
  │           ├── BrokerService()
  │           ├── validate_production_config()
  │           ├── assert_runtime_parity_or_raise()
  │           ├── Wire gateway, TradingContext, Orchestrator
  │           └── Return Runtime dataclass
  │
  └── Rich/TUI commands dispatch
        ├── broker commands → cli/services/broker_service.py
        ├── order commands  → application/oms/ + application/execution/
        ├── analytics       → analytics/
        ├── doctor          → cli/diagnostics/ + cli/commands/doctor/
        └── TUI widgets     → cli/widgets/
```

### 3.4 Order Placement Flow

```
HTTP POST /api/v1/orders                             # api/routers/orders.py
    │
    ▼
place_order(req: OrderRequest, composer=Depends(get_execution_composer))
    │
    ▼
Convert to DomainOrderRequest
    │
    ▼
ExecutionComposer.place_order(domain_req)            # application/composer/execution.py
    │
    ├── 1. Route to broker                           # brokers/common/router.py
    │      BrokerRouter.route(RoutingRequest)
    │      → Filters by capability, health, quota headroom
    │      → Returns RouteDecision(primary_broker="dhan")
    │
    ├── 2. Acquire quota                             # brokers/common/quota_scheduler.py
    │      QuotaScheduler.acquire_async()
    │      → Checks rate limit budget
    │      → Returns QuotaToken
    │
    ├── 3. Execute                                   # brokers/{dhan|upstox}/gateway.py
    │      gateway.place_order(request, quota=quota)
    │      → Broker adapter makes API call
    │      → Retry/circuit breaker via resilience layer
    │
    └── 4. Return OrderResponse with broker-assigned order_id

[OMS Processing — if wired via event bus]
    │
    ▼
OrderManager.place_order()                           # application/oms/order_manager.py
    │
    ├── Phase 1: Idempotency check (under lock)
    │   ├── Check correlation_id in _orders_by_correlation
    │   └── Reserve correlation_id in _pending_correlation
    │
    ├── Phase 2: Build & validate (no lock)
    │   ├── Check placement gate
    │   ├── Build Order entity
    │   └── RiskManager.check_order()
    │       → publishes RISK_APPROVED / RISK_REJECTED events
    │
    ├── Phase 3: Submit to broker (no lock)
    │   └── submit_fn(request) → broker adapter
    │
    └── Phase 4: Record & publish (under lock)
        ├── Insert into _orders dict
        ├── Publish ORDER_PLACED event
        └── Persist to SqliteOrderStore
```

### 3.5 Trade Processing Flow

```
Broker WebSocket receives fill
    │
    ▼
Broker adapter publishes TRADE event
    │
    ▼
EventBus.publish(DomainEvent.now("TRADE", {"trade": trade}))
    │                                                # infrastructure/event_bus/event_bus.py
    ├── 1. Prepare event: inject correlation_id, assign sequence_number
    ├── 2. Idempotency check: skip if event_id already processed
    ├── 3. Persist to event log (crash recovery)
    └── 4. Dispatch to subscribers
    │
    ▼
OrderManager.on_trade(event)                         # application/oms/order_manager.py
    │
    ├── 1. Validate trade idempotency (ProcessedTradeRepository)
    ├── 2. Update order filled_quantity, average_price
    ├── 3. Publish ORDER_UPDATED event
    └── 4. Publish TRADE_APPLIED event (OMS-private, downstream of TRADE)
    │
    ▼
PositionManager.on_trade_applied(event)              # application/oms/position_manager.py
    │
    ├── 1. Calculate delta: +quantity for BUY, -quantity for SELL
    ├── 2. Determine position state transition (FLAT→OPEN, OPEN→CLOSED, etc.)
    ├── 3. Validate state transition (StateMachine)
    ├── 4. Update position: with_fill(delta, price)
    └── 5. Publish POSITION_OPENED / POSITION_CLOSED / POSITION_UPDATED events
```

### 3.6 WebSocket Market Data Flow

```
Client connects to ws://host/ws/market               # api/ws/market.py
    │
    ▼
market_websocket(websocket: WebSocket)
    │
    ├── 1. Auth check: reject_ws_if_unauthorized(websocket)
    ├── 2. Generate connection_id (UUID)
    └── 3. market_manager.connect(websocket, connection_id)
    │
    ▼
Client sends: {"action": "subscribe", "symbols": ["RELIANCE", "TCS"]}
    │
    ├── 4. Parse action, extract symbols
    ├── 5. market_manager.subscribe(connection_id, symbols)
    └── 6. subscribe_symbols_to_broker(symbols)
           → Wires broker WebSocket to EventBus
    │
    ▼
[MarketBridge]                                       # api/ws/bridge.py
    │
    ├── 1. Subscribes to TICK, QUOTE, DEPTH, TRADE events
    ├── 2. on_event callback puts event into asyncio.Queue
    │      (drop-oldest policy when queue full)
    ├── 3. _dispatch_loop() reads from queue
    └── 4. For each connected client:
           ├── Check if event.symbol in client's subscriptions
           ├── Format message: _format_message(event)
           └── send_to_client(connection_id, msg)
    │
    ▼
Client receives: {"type": "tick", "symbol": "RELIANCE", "ltp": 2450.50, ...}
```

### 3.7 Historical Data Flow

```
HTTP GET /api/v1/market/historical                   # api/routers/market.py
  ?symbol=RELIANCE&timeframe=1m&from_date=...
    │
    ▼
get_historical_data(composer=Depends(get_market_data_composer))
    │
    ▼
MarketDataComposer.get_historical_bars(...)          # application/composer/market_data.py
    │
    ▼
[HistoricalDataCoordinator]                          # brokers/common/historical_coordinator.py
    │
    ├── 1. Plan: Determine which broker(s) can serve the request
    │      → Check capabilities, date ranges, data availability
    │
    ├── 2. Chunk: Split request into broker-specific slices
    │
    ├── 3. Route: BrokerRouter selects broker for each chunk
    │
    ├── 4. Acquire quota: QuotaScheduler.acquire() for each broker
    │
    ├── 5. Fetch: gateway.get_historical_bars(request, quota=quota)
    │      → Broker adapter makes API call
    │      → Retry with exponential backoff on failure
    │
    └── 6. Merge: Combine results from multiple brokers
           → Deduplicate, sort by timestamp
           → Fill gaps if needed
    │
    ▼
Return list[HistoricalBar]
```

### 3.8 Multi-Broker Execution Flow (ExecutionComposer)

```
ExecutionComposer.place_order(request, broker_id=None)   # application/composer/execution.py
    │
    ├── 1. Route: self._route_order()
    │      → BrokerRouter.route(RoutingRequest(operation=PLACE_ORDER))
    │      → Filters candidates by capability, health
    │      → Scores by quota headroom (if quota_aware policy)
    │      → Returns RouteDecision(primary_broker="dhan")
    │
    ├── 2. Acquire quota: self._acquire_quota("dhan", "orders", "EXECUTION_CRITICAL")
    │      → QuotaScheduler.acquire_async() → QuotaToken
    │      → Checks rate limit budget
    │      → Reserves quota for this operation
    │
    ├── 3. Execute: gateway.place_order(request, quota=quota)
    │      → BrokerRegistry.get_gateway("dhan") → DhanGateway
    │      → DhanGateway.place_order() → broker API call
    │      → Retry/circuit breaker via resilience layer
    │
    └── 4. Return OrderResponse with broker-assigned order_id
```



---

## 4. Cross-Cutting Concerns

### 4.1 Exception Handling

**File:** `infrastructure/global_exception_handler.py`

Two-tier exception handling registered on the FastAPI app via `setup_exception_handlers(app)`:

#### Tier 1: TradeXV2Error Hierarchy → HTTP Status Mapping

| Exception Class | HTTP Status | Error Type |
|---|---|---|
| `AuthenticationError` | 401 | `broker_auth_error` |
| `RateLimitError` | 429 | `rate_limit_exceeded` |
| `OrderError` | 400 | `order_execution_error` |
| `CircuitBreakerOpenError` | 503 | `service_unavailable` |
| `BrokerDegradedError` | 503 | `service_unavailable` |
| `InstrumentNotFoundError` | 404 | `instrument_not_found` |
| `ValidationError` | 422 | `validation_error` |
| `NotSupportedError` | 501 | `not_supported` |
| `DataError` | 500 | `data_error` |
| `ConfigError` | 500 | `config_error` |
| `RetryableError` | 503 | `recoverable_error` |
| `NonRetryableError` | 500 | `fatal_error` |
| `BrokerError` | 502 | `broker_error` |
| `TradeXV2Error` (default) | 500 | `tradexv2_error` |

#### Tier 2: Generic Exception Fallback

- Catches unexpected `Exception` subclasses
- Returns 500 with generic message `"An unexpected error occurred"`
- Includes exception type in response only when `TRADEXV2_DEBUG=true`

#### Structured Error Response Format

```json
{
  "error": {
    "type": "order_execution_error",
    "message": "Insufficient margin",
    "status_code": 400,
    "details": {}
  },
  "correlation_id": "1719750930123-abc123def456"
}
```

#### Exception Hierarchy Source

All exception classes are defined in `brokers/common/resilience/errors.py`:

```
TradeXV2Error (base)
├── BrokerError
│   ├── AuthenticationError
│   ├── RateLimitError
│   ├── CircuitBreakerOpenError
│   └── BrokerDegradedError
├── OrderError
├── InstrumentNotFoundError
├── ValidationError
├── NotSupportedError
├── DataError
├── ConfigError
├── RetryableError (TradeXV2RecoverableError)
└── NonRetryableError
```

---

### 4.2 Logging Configuration

**File:** `infrastructure/logging_config.py`

#### Dual-Mode Logging

| Mode | Formatter | When Active |
|---|---|---|
| **Production** | `StructuredFormatter` — JSON structured logs | `APP_ENV=prod` or `APP_ENV=production` |
| **Development** | `HumanReadableFormatter` — colored console output | All other environments |

#### Configuration Entry Point

```python
configure_logging(
    service="api",            # Service name for log identification
    level="INFO",             # Or from XV2_LOG_LEVEL env var
    log_format="json",        # Or "human"; auto-detected if None
    log_file=None,            # Optional RotatingFileHandler path
    enable_redaction=True,    # Token redaction (REF-29)
)
```

#### Token Redaction Filter (REF-29)

`TokenRedactionFilter` redacts sensitive patterns from both log messages AND structured extra fields:

**Redacted patterns:**
- `access_token=...`, `refresh_token=...`, `api_key=...`, `api_secret=...`
- `password=...`, `authorization: Bearer ...`
- URL query params `?token=...`
- Broker-specific tokens: `DHAN_*TOKEN`, `UPSTOX_*TOKEN`, etc.
- Any alphanumeric string ≥ 32 characters

**Redacted extra keys:** `token`, `access_token`, `refresh_token`, `api_key`, `api_secret`, `password`, `pin`, `totp`, `totp_secret`, `authorization`, `bearer_token`, and any key ending with `_token`

#### Correlation ID Injection

`CorrelationFilter` injects `correlation_id` and `service_name` into every `LogRecord` via `infrastructure.correlation.get_current_correlation_id()`.

#### Production JSON Log Example

```json
{
  "timestamp": "2026-06-30T10:15:30.123456+00:00",
  "service": "api",
  "level": "INFO",
  "logger": "application.oms.order_manager",
  "message": "Order placed",
  "module": "order_manager",
  "function": "place_order",
  "line": 420,
  "thread": "MainThread",
  "process": 12345,
  "correlation_id": "1719750930123-abc123def456",
  "service_name": "api",
  "order_id": "OM-abc123",
  "symbol": "RELIANCE"
}
```

#### Third-Party Logger Suppression

Loggers for `urllib3`, `httpx`, `websockets`, `asyncio` are forced to `WARNING` level to reduce noise.

---

### 4.3 Middleware Chain

**File:** `api/middleware.py`

Applied in order (outermost → innermost):

```
Request → CORSMiddleware → RateLimitMiddleware → RequestLoggingMiddleware → Router
```

#### 4.3.1 CORSMiddleware

- Configurable origins, methods, headers
- Credentials support
- Configured in `api/main.py`

#### 4.3.2 RateLimitMiddleware

- **Algorithm:** Per-IP sliding window using `_SlidingWindowCounter`
- **Configuration:** `max_requests` (default 0 = disabled), `window_seconds` (default 60)
- **Client IP extraction:** Prefers `X-Forwarded-For` header, falls back to `request.client.host`
- **On deny:** Returns HTTP 429 with headers:
  - `Retry-After: {window_seconds}`
  - `X-RateLimit-Limit: {max_requests}`
  - `X-RateLimit-Remaining: 0`
  - `X-RateLimit-Window: {window_seconds}`
- **Skips:** Health probes, WebSocket upgrade requests

#### 4.3.3 RequestLoggingMiddleware

- **Correlation ID:** Extracts from `X-Request-ID` or `X-Correlation-ID` header; generates UUID if absent
- **Path normalization:** `/orders/123` → `/orders/{id}` (strips numeric segments for cardinality control)
- **Active request tracking:** `http_metrics.inc_active()` / `dec_active()`
- **Logging:** `METHOD /path STATUS DURATIONms [request_id]`
- **Prometheus metrics:** Records to `HttpRequestMetrics` singleton
- **Skips:** `/`, `/docs`, `/openapi.json`, `/redoc`, `/api/v1/health/*`

#### 4.3.4 HTTP Metrics (Prometheus)

`HttpRequestMetrics` (singleton at `api/middleware.http_metrics`):

| Metric | Type | Labels |
|---|---|---|
| `tradexv2_http_requests_total` | Counter | `method`, `path`, `status` |
| `tradexv2_http_request_duration_ms_sum` | Counter | `method`, `path`, `status` |
| `tradexv2_http_request_duration_ms_count` | Counter | `method`, `path`, `status` |
| `tradexv2_http_active_requests` | Gauge | — |

Exposed via `render_prometheus()` at `/api/v1/health/metrics/prometheus`.

---

### 4.4 Retry Framework

**File:** `infrastructure/retry.py`

#### RetryPolicy Dataclass

```python
@dataclass
class RetryPolicy:
    max_attempts: int = 3                    # Including first try
    backoff_factor: float = 2.0              # Multiplier for delay
    initial_delay: float = 1.0               # Seconds
    max_delay: float = 60.0                  # Cap
    backoff_strategy: BackoffStrategy = EXPONENTIAL
    retryable_exceptions: tuple = (TradeXV2RecoverableError,)
    jitter: bool = True                      # ±10% random jitter
```

#### Backoff Strategies

| Strategy | Formula |
|---|---|
| `FIXED` | `initial_delay` (constant) |
| `LINEAR` | `initial_delay × (attempt + 1)` |
| `EXPONENTIAL` | `initial_delay × (backoff_factor ^ attempt)` |
| `RANDOM` | `uniform(initial_delay, max_delay)` |

All strategies are capped at `max_delay` and optionally jittered by ±10%.

#### Pre-defined Policies

| Name | Max Attempts | Initial Delay | Backoff Factor | Max Delay |
|---|---|---|---|---|
| `default` | 3 | 1.0s | 2.0 | 60.0s |
| `aggressive` | 5 | 0.5s | 2.0 | 30.0s |
| `conservative` | 2 | 2.0s | 1.5 | 60.0s |
| `fast` | 3 | 0.1s | 1.0 | 5.0s |
| `slow` | 10 | 5.0s | 3.0 | 300.0s |

#### Safety Guards

- **Double-wrap detection:** Raises `TypeError` if `@retry` is applied twice to the same function
- **Nesting detection:** Logs `retry.nested` warning if `@retry` function is called from inside another `@retry` loop

#### Usage

```python
@retry                                          # Default policy
async def call_broker(): ...

@retry(policy=RetryPolicy(max_attempts=5))      # Custom policy
def call_database(): ...

@retry(policy="aggressive")                     # Named policy
async def call_external(): ...
```

---

### 4.5 Caching

**File:** `infrastructure/cache.py`

#### Abstract Interface

```python
class Cache(ABC):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
    def has(self, key: str) -> bool: ...
```

#### MemoryCache Implementation

- Thread-safe via `threading.RLock`
- TTL-based expiration using `time.monotonic()`
- Default TTL: 300 seconds
- Prometheus metrics: `cache_hits_total`, `cache_misses_total`, `cache_evictions_total`, `cache_size`

#### Decorators

```python
@cached(cache=None, ttl=300)          # Sync function caching
@async_cached(cache=None, ttl=300)    # Async function caching
```

---

### 4.6 Correlation ID Propagation

**File:** `infrastructure/correlation.py`

- Uses `contextvars.ContextVar` for async-safe propagation across task boundaries
- ID format: `{timestamp_ms}-{uuid_short}` (e.g., `1719750930123-abc123def456`)

#### Integration Points

| Component | Behavior |
|---|---|
| `RequestLoggingMiddleware` | Extracts from `X-Request-ID` header or generates new |
| `DomainEvent.now()` | Auto-injects from current context |
| `CorrelationFilter` (logging) | Injects into every log record |
| Exception handler | Includes in error responses |

#### Context Manager

```python
with with_correlation() as cid:    # Auto-generates ID
    # All code here sees this correlation ID
    ...
```

---

### 4.7 Tracing Decorators

**File:** `infrastructure/tracing.py`

```python
@trace_operation("order_placement")   # Logs start/end, duration_ms, status
def place_order(request): ...

@trace_event_handler("ORDER_UPDATED") # Logs handler processing duration
def on_order_update(event): ...
```

---

### 4.8 State Machine

**File:** `infrastructure/state_machine.py`

Generic state machine with explicit transition validation:

```python
class StateMachine(Generic[T]):
    def __init__(self, transitions: dict[T, frozenset[T]], initial: T): ...
    def can_transition_to(self, new_state: T) -> bool: ...
    def transition_to(self, new_state: T) -> None: ...  # Raises IllegalTransitionError
    def reset(self, new_state: T | None = None) -> None: ...
    @property
    def is_terminal(self) -> bool: ...
```

**Used by:**
- Order lifecycle: `OPEN → PARTIALLY_FILLED → FILLED` (terminal)
- Position lifecycle: `FLAT → OPEN → REDUCING → CLOSED` (terminal)
- Scanner lifecycle: `IDLE → RUNNING → COMPLETED`
- Strategy lifecycle: `INACTIVE → ACTIVE → DISABLED`

**Error:** `IllegalTransitionError(from_state, to_state)` — extends `TradeXV2Error`



---

## 5. Domain Object Details

### 5.1 Entity Catalog

All entities are `@dataclass(slots=True, frozen=True)` — immutable value objects.

#### 5.1.1 Order — `domain/entities/order.py`

| Field | Type | Default | Description |
|---|---|---|---|
| `order_id` | `str` | *(required)* | Unique order identifier |
| `symbol` | `str` | *(required)* | Trading symbol |
| `exchange` | `str` | *(required)* | Exchange code |
| `side` | `Side` | *(required)* | BUY or SELL |
| `order_type` | `OrderType` | *(required)* | LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET |
| `quantity` | `int` | *(required)* | Order quantity |
| `filled_quantity` | `int` | `0` | Quantity filled so far |
| `price` | `Decimal` | `Decimal("0")` | Limit price |
| `trigger_price` | `Decimal` | `Decimal("0")` | Stop-loss trigger |
| `status` | `OrderStatus` | `OrderStatus.OPEN` | Current order status |
| `timestamp` | `datetime \| None` | `None` | Order timestamp |
| `product_type` | `ProductType` | `ProductType.INTRADAY` | CNC, INTRADAY, MARGIN, MTF |
| `validity` | `Validity` | `Validity.DAY` | DAY or IOC |
| `avg_price` | `Decimal` | `Decimal("0")` | Average fill price |
| `reject_reason` | `str` | `""` | Rejection reason |
| `correlation_id` | `str \| None` | `None` | Cross-system correlation |
| `instrument_id` | `str \| None` | `None` | Canonical ID (e.g., `NSE:RELIANCE`) |

**Properties:** `average_price`, `remaining_quantity`, `is_complete`
**Methods:** `with_status(status)`, `with_fill(filled_quantity, avg_price)`, `from_broker_dict(d, field_mapping, exchange_resolver)`

#### 5.1.2 OrderResponse — `domain/entities/order.py`

| Field | Type | Default |
|---|---|---|
| `success` | `bool` | *(required)* |
| `order_id` | `str` | `""` |
| `message` | `str` | `""` |
| `status` | `OrderStatus` | `OrderStatus.OPEN` |
| `broker_order_id` | `str` | `""` |
| `error_code` | `str` | `""` |
| `http_status` | `int \| None` | `None` |
| `raw_payload` | `dict[str, Any] \| None` | `None` |
| `latency_ms` | `float` | `0.0` |

**Class methods:** `ok(...)`, `fail(...)` · **Instance methods:** `with_broker_id(broker_id)`

#### 5.1.3 Position — `domain/entities/position.py`

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | *(required)* |
| `exchange` | `str` | *(required)* |
| `quantity` | `int` | `0` |
| `avg_price` | `Decimal` | `Decimal("0")` |
| `ltp` | `Decimal` | `Decimal("0")` |
| `unrealized_pnl` | `Decimal` | `Decimal("0")` |
| `realized_pnl` | `Decimal` | `Decimal("0")` |
| `product_type` | `ProductType` | `ProductType.INTRADAY` |
| `correlation_id` | `str \| None` | `None` |

**Properties:** `pnl` (computed from quantity × price delta)
**Methods:** `with_ltp(ltp)`, `with_fill(quantity, price)` — both return new instances with updated PnL

#### 5.1.4 Holding — `domain/entities/position.py`

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | *(required)* |
| `exchange` | `str` | *(required)* |
| `quantity` | `int` | `0` |
| `available_quantity` | `int` | `0` |
| `avg_price` | `Decimal` | `Decimal("0")` |
| `ltp` | `Decimal` | `Decimal("0")` |
| `pnl` | `Decimal` | `Decimal("0")` |
| `correlation_id` | `str \| None` | `None` |

#### 5.1.5 Trade — `domain/entities/trade.py`

| Field | Type | Default |
|---|---|---|
| `trade_id` | `str` | *(required)* |
| `order_id` | `str` | *(required)* |
| `symbol` | `str` | *(required)* |
| `exchange` | `str` | *(required)* |
| `side` | `Side` | *(required)* |
| `quantity` | `int` | *(required)* |
| `price` | `Decimal` | `Decimal("0")` |
| `trade_value` | `Decimal` | `Decimal("0")` |
| `timestamp` | `datetime \| None` | `None` |
| `product_type` | `ProductType` | `ProductType.INTRADAY` |
| `correlation_id` | `str \| None` | `None` |

**Properties:** `value` — returns `trade_value` if > 0, else `price × quantity`

#### 5.1.6 Balance (FundLimits) — `domain/entities/account.py`

| Field | Type | Default |
|---|---|---|
| `available_balance` | `Decimal` | `Decimal("0")` |
| `used_margin` | `Decimal` | `Decimal("0")` |
| `total_margin` | `Decimal` | `Decimal("0")` |
| `sod_limit` | `Decimal` | `Decimal("0")` |
| `collateral_amount` | `Decimal` | `Decimal("0")` |
| `utilized_amount` | `Decimal` | `Decimal("0")` |
| `withdrawable_balance` | `Decimal` | `Decimal("0")` |

**Methods:** `has_sufficient(required) → bool`

#### 5.1.7 Instrument — `domain/entities/instrument.py`

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | *(required)* |
| `exchange` | `str` | *(required)* |
| `security_id` | `str` | *(required)* |
| `instrument_type` | `str` | *(required)* |
| `lot_size` | `int` | `1` |
| `tick_size` | `Decimal` | `0.05` |
| `name` | `str \| None` | `None` |
| `option_type` | `str \| None` | `None` |
| `strike_price` | `Decimal \| None` | `None` |
| `expiry` | `str \| None` | `None` |
| `underlying` | `str \| None` | `None` |
| `canonical_symbol` | `str \| None` | `None` |

#### 5.1.8 Market Data Entities — `domain/entities/market.py`

**DepthLevel** (`@dataclass(frozen=True)`)

| Field | Type | Default |
|---|---|---|
| `price` | `Decimal` | `Decimal("0")` |
| `quantity` | `int` | `0` |
| `orders` | `int` | `0` |

**MarketDepth** (`@dataclass(frozen=False)` — mutable bid/ask lists)

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | `""` |
| `bids` | `list[DepthLevel] \| None` | `[]` |
| `asks` | `list[DepthLevel] \| None` | `[]` |
| `timestamp` | `datetime \| None` | `None` |
| `depth_type` | `str` | `"DEPTH_5"` |

**Quote** (`@dataclass(frozen=True)`)

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | *(required)* |
| `ltp` | `Decimal` | `Decimal("0")` |
| `open/high/low/close` | `Decimal` | `Decimal("0")` |
| `volume` | `int` | `0` |
| `change` | `Decimal` | `Decimal("0")` |
| `bid/ask` | `Decimal \| None` | `None` |
| `timestamp` | `datetime \| None` | `None` |

**MarketTick** (provenance-aware, `@dataclass(frozen=True)`)

| Field | Type | Default |
|---|---|---|
| `instrument` | `InstrumentRef` | *(required)* |
| `ltp` | `Decimal` | *(required)* |
| `event_time` | `datetime` | *(required)* |
| `provenance` | `DataProvenance` | *(required)* |
| `volume` | `int` | `0` |
| `bid/ask` | `Decimal \| None` | `None` |
| `sequence` | `int \| None` | `None` |
| `open/high/low` | `Decimal \| None` | `None` |

**QuoteSnapshot** (provenance-aware, `@dataclass(frozen=True)`)

| Field | Type | Default |
|---|---|---|
| `instrument` | `InstrumentRef` | *(required)* |
| `ltp` | `Decimal` | *(required)* |
| `event_time` | `datetime` | *(required)* |
| `provenance` | `DataProvenance` | *(required)* |
| `open/high/low/close` | `Decimal` | `Decimal("0")` |
| `volume` | `int` | `0` |
| `change_pct` | `Decimal` | `Decimal("0")` |
| `bid/ask` | `Decimal \| None` | `None` |

#### 5.1.9 Options/Futures Entities — `domain/entities/options.py`

**OptionContract** (`@dataclass(frozen=True)`)

| Field | Type | Default |
|---|---|---|
| `strike` | `Decimal` | `Decimal("0")` |
| `expiry` | `str` | `""` |
| `instrument_type` | `str` | `"OPTION"` |
| `exchange` | `str` | `"NFO"` |
| `lot_size` | `int` | `0` |
| `call_ltp/call_bid/call_ask/call_iv` | `Decimal \| None` | `None` |
| `call_oi/call_volume` | `int \| None` | `None` |
| `put_ltp/put_bid/put_ask/put_iv` | `Decimal \| None` | `None` |
| `put_oi/put_volume` | `int \| None` | `None` |

**OptionLeg** · **OptionStrike** · **OptionChain** — all `@dataclass(frozen=True)` with `from_dict()` / `to_dict()` methods

**FutureContract** · **FutureChain** — all `@dataclass(frozen=True)` with `from_dict()` / `to_dict()` methods

#### 5.1.10 Alert & PnL Entities — `domain/entities/alerts.py`

| Entity | Key Fields |
|---|---|
| `ConditionalAlert` | `alert_id`, `symbol`, `condition`, `status` |
| `ConditionalAlertRequest` | `symbol`, `exchange`, `condition_type`, `threshold` |
| `MarketIntelligenceSnapshot` | `underlying`, `pcr`, `max_pain`, `oi_data` (mutable) |
| `PnlExitPolicy` | `target_pnl`, `stop_loss` |
| `PnlExitResult` | `success`, `message` |

---

### 5.2 Value Objects

#### 5.2.1 InstrumentId — `domain/instrument_id.py`

`@dataclass(frozen=True, order=True)` — Immutable, hashable, ordered

| Field | Type | Default |
|---|---|---|
| `exchange` | `str` | *(required)* |
| `underlying` | `str` | *(required)* |
| `expiry` | `date \| None` | `None` |
| `strike` | `Decimal \| None` | `None` |
| `right` | `str \| None` | `None` |

**Factory methods:** `equity(exchange, symbol)`, `index(exchange, name)`, `future(exchange, underlying, expiry)`, `option(exchange, underlying, expiry, strike, right)`
**Properties:** `asset_type`, `is_equity`, `is_index`, `is_future`, `is_option`, `is_call`, `is_put`, `key`
**Format examples:** `NSE:RELIANCE`, `NFO:NIFTY:20260730:FUT`, `NFO:NIFTY:20260730:25000:CE`

#### 5.2.2 Historical Models — `domain/historical.py`

**InstrumentRef** — `symbol: str`, `exchange: str` (frozen, slots)

**HistoricalBar** — `instrument: InstrumentRef`, `timeframe: str`, `event_time: datetime`, `open/high/low/close: Decimal`, `volume: int`, `provenance: DataProvenance`, `open_interest: int = 0`, `bar_index: int = 0`, `is_partial: bool = False`, `label_convention: BarLabelConvention = LEFT`

**HistoricalSeries** — `bars: list[HistoricalBar]`, `coverage: DateRange`, `instrument: InstrumentRef`, `timeframe: str`, `gaps: list[Gap]`, `merge_manifest: MergeManifest | None`
- Properties: `is_complete`, `is_degraded`, `bar_count`
- Methods: `brokers_contributing() → set[str]`

**DateRange** — `start: date`, `end: date` · Methods: `days() → int`, `__contains__(d)`

**Gap** — `start: date`, `end: date`, `reason: str = "no_data"`

#### 5.2.3 Provenance Models — `domain/provenance.py`

**SourceIdentity** — `broker_id: str`, `account_id: str | None`, `connection_id: str | None`

**TimestampSemantics** — `event_time: datetime`, `ingest_time: datetime`, `effective_time: datetime`

**DataProvenance** — `source: SourceIdentity`, `fetched_at: datetime`, `request_id: str`, `confidence: ProvenanceConfidence = AUTHORITATIVE`, `provider_timestamp: datetime | None`, `transformation_chain: tuple[str, ...]`
- Methods: `now(broker_id, request_id, ...)`, `with_transformation(step)`, `as_merged()`, `as_fallback()`

#### 5.2.4 GatewayResult[T] — `domain/result.py`

Generic monadic result with: `is_success`, `is_failure`, `value`, `error`, `metadata`
Methods: `map(fn)`, `flat_map(fn)`, `recover(fn)`, `get_or_else(default)`

#### 5.2.5 Reconciliation Models — `domain/reconciliation.py`

**DriftItem** — `kind: str`, `severity: str`, `symbol: str`, `details: str`, `payload: dict | None`

**ReconciliationReport** — `drift_items: list[DriftItem]`, `broker_orders: int`, `broker_positions: int`, `orders_repaired: int`, `positions_repaired: int`, `timestamp_ms: int`
- Properties: `has_drift`, `high_severity_count`

#### 5.2.6 Trading DTOs — `domain/models/trading.py`

**CandidateDTO** — `symbol`, `exchange`, `score: Decimal`, `metrics: dict`, `reasons: list[str]`, `strategy_id`, `timestamp`

**SignalDTO** — `symbol`, `exchange`, `side`, `signal_type`, `confidence: Decimal`, `quantity: int`, `price: Decimal | None`, `entry_price: Decimal | None`, `strategy: str`, `position_size_pct: Decimal`
- Property: `is_actionable` — True if `signal_type ∈ {BUY, SELL, STRONG_BUY, STRONG_SELL, ENTRY, EXIT}` and `confidence > 0`

#### 5.2.7 FeatureSet — `domain/models/features.py`

`@dataclass(frozen=True)` — Immutable, pandas-free columnar container
- Fields: `columns: dict[str, list]`, `index: list`
- Properties: `row_count`, `column_names`, `is_empty`
- Methods: `empty()`, `tail(n)`, `__getitem__(col)`, `__contains__(col)`

#### 5.2.8 Stream Health Models — `domain/stream_health.py`

**StreamHealth** — `transport: TransportState`, `subscription: SubscriptionState`, `freshness: FreshnessState`, `last_message_at: datetime | None`, `last_valid_tick_at: datetime | None`, `stale_seconds_threshold: float = 30.0`
- Methods: `healthy() → bool`, `failure_reasons() → list[str]`

**StreamSession** — `session_id`, `broker_id`, `stream_kind`, `instruments: frozenset[str]`, `modes: frozenset[str]`, `health: StreamHealth`, `reconnect_generation: int`, `created_at`, `last_state_change_at`

**StreamStateSummary** — `broker_id`, `active_sessions`, `healthy_sessions`, `stale_sessions`, `degraded_sessions`

#### 5.2.9 Other Value Objects

| Object | File | Key Fields |
|---|---|---|
| `HealthStatus` | `domain/lifecycle_health.py` | `state: HealthState`, `service: str`, `detail: str`, `last_check: datetime`, `metrics: dict` |
| `RuntimeHooks` | `domain/runtime_hooks.py` | `oms_backtest_factory`, `domain_event_factory`, `trading_context_factory` |
| `IndianMarketFees` | `domain/trading_costs.py` | `brokerage_pct=0.03`, `brokerage_max=20.0`, `stt_pct_sell_delivery=0.1`, `gst_pct=18.0`, etc. |
| `CapabilitySurface` | `domain/capability_manifest.py` | `id`, `capability`, `gateway_method`, `abc_required`, `tier`, `severity_if_gap` |
| `CliExposure` / `RestExposure` | `domain/capability_manifest.py` | `command/module` and `method/path/module/data_source` |

---

### 5.3 Enums Catalog

#### Core Trading Enums — `domain/enums.py`

| Enum | Values |
|---|---|
| `Side` | `BUY`, `SELL` |
| `OrderStatus` | `OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`, `EXPIRED`, `UNKNOWN` |
| `ProductType` | `CNC`, `INTRADAY`, `MARGIN`, `MTF` |
| `OrderType` | `LIMIT`, `MARKET`, `STOP_LOSS`, `STOP_LOSS_MARKET` |
| `Validity` | `DAY`, `IOC` |

**OrderStatus properties:** `is_terminal` → True for {FILLED, CANCELLED, REJECTED, EXPIRED}
**OrderStatus methods:** `normalize(raw: str) → OrderStatus` (delegates to `StatusMapperRegistry`)

#### Market Enums — `domain/market_enums.py`

| Enum | Values |
|---|---|
| `ExchangeSegment` | `NSE = "NSE_EQ"`, `BSE = "BSE_EQ"`, `NSE_FNO = "NSE_FNO"`, `BSE_FNO = "BSE_FNO"`, `MCX = "MCXCOMM"`, `NSE_CURRENCY = "NSE_CURRENCY"`, `BSE_CURRENCY = "BSE_CURRENCY"`, `IDX_I = "IDX_I"` |
| `InstrumentType` | `EQUITY`, `FUTURES`, `OPTIONS`, `CURRENCY`, `COMMODITY`, `INDEX` |

#### Capability Enums — `domain/capabilities.py`

| Enum | Values (55 total) |
|---|---|
| `Capability` | `MARKET_DATA`, `ORDER_COMMAND`, `ORDER_QUERY`, `PORTFOLIO`, `OPTIONS_CHAIN`, `INSTRUMENTS`, `FUTURES`, `HISTORICAL_DATA`, `WEBSOCKET`, `COVER_ORDER`, `GTT_ORDER`, `SLICE_ORDER`, `MARGIN`, `NEWS`, `SESSION_RISK`, `ALERTS`, `MARKET_STATUS`, `DEPTH`, `ORDER_STREAM`, `IDEMPOTENCY`, `MULTI_ORDER`, `KILL_SWITCH`, `STATIC_IP`, `SMARTLIST`, `FII_DII`, `OI_PCR_MAXPAIN`, `MARKET_INTELLIGENCE`, `FUNDAMENTALS`, `IPO`, `MUTUAL_FUNDS`, `PAYMENTS`, `INSTRUMENT_SEARCH`, `HISTORICAL_TRADES`, `TSL`, `MTF`, `WEBHOOKS`, `AMO_ORDER`, `EXIT_ALL`, `PORTFOLIO_STREAM`, `ORDER_SLICING`, `DEPTH_30`, `LEVEL2_MARKET_DATA`, `OPTION_GREEKS`, `GLOBAL_MARKETS`, `VOLATILITY_INDEX` |
| `ConnectionStatus` | `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `RECONNECTING` |

#### Position & Market Enums

| Enum | File | Values |
|---|---|---|
| `PositionState` | `domain/entities/position.py` | `FLAT`, `OPEN`, `REDUCING`, `CLOSED`, `REVERSED` |
| `DepthKind` | `domain/entities/market.py` | `REST_5`, `WS_20`, `WS_200` |

#### Historical & Provenance Enums

| Enum | File | Values |
|---|---|---|
| `BarLabelConvention` | `domain/historical.py` | `LEFT`, `RIGHT`, `CENTER` |
| `ProvenanceConfidence` | `domain/provenance.py` | `AUTHORITATIVE`, `DERIVED`, `MERGED`, `FALLBACK` |

#### Stream Health Enums — `domain/stream_health.py`

| Enum | Values |
|---|---|
| `TransportState` | `DISCONNECTED`, `CONNECTING`, `AUTHENTICATING`, `CONNECTED`, `RECONNECTING` |
| `SubscriptionState` | `IDLE`, `SUBSCRIBING`, `ACKNOWLEDGED`, `PARTIAL`, `DEGRADED` |
| `FreshnessState` | `UNKNOWN`, `FRESH`, `STALE`, `NO_DATA` |

#### Health & Cost Enums

| Enum | File | Values |
|---|---|---|
| `HealthState` | `domain/lifecycle_health.py` | `STOPPED`, `STARTING`, `HEALTHY`, `DEGRADED`, `UNHEALTHY`, `STOPPING`, `FAILED` |
| `CommissionModel` | `domain/trading_costs.py` | `FLAT`, `INDIAN_EQUITY`, `INDIAN_FNO` |
| `SlippageModel` | `domain/trading_costs.py` | `FIXED_PCT`, `VOLUME_WEIGHTED` |

---

### 5.4 Domain Events — `domain/events/types.py`

#### EventType Enum (53 event types)

| Category | Event Types |
|---|---|
| **Market Data** | `TICK`, `DEPTH`, `INDEX_QUOTE`, `OPTION_CHAIN` |
| **Orders/OMS** | `ORDER_PLACED`, `ORDER_SUBMITTED`, `ORDER_UPDATED`, `ORDER_CANCELLED`, `ORDER_REJECTED`, `TRADE`, `TRADE_APPLIED` |
| **Risk/Position** | `POSITION_CHANGED`, `RISK_BREACH`, `KILL_SWITCH_FLIPPED`, `RISK_APPROVED`, `RISK_REJECTED` |
| **Position Lifecycle** | `POSITION_OPENED`, `POSITION_CLOSED` |
| **Reconciliation** | `RECONCILIATION_DRIFT`, `RECONCILIATION_OK` |
| **Lifecycle** | `SERVICE_STARTED`, `SERVICE_STOPPED`, `SERVICE_FAILED`, `SYSTEM_STARTED`, `SYSTEM_SHUTDOWN` |
| **Broker Connectivity** | `BROKER_CONNECTED`, `BROKER_DISCONNECTED`, `TOKEN_REFRESHED`, `TOKEN_EXPIRED`, `CIRCUIT_BREAKER_OPENED`, `CIRCUIT_BREAKER_CLOSED` |
| **Scanner** | `SCAN_STARTED`, `CANDIDATE_GENERATED`, `SCAN_COMPLETED`, `SCANNER_STATE_CHANGED` |
| **Strategy** | `SIGNAL_EXECUTED`, `STRATEGY_ACTIVATED`, `STRATEGY_PAUSED`, `STRATEGY_DISABLED` |
| **Risk Decision** | `RISK_APPROVED`, `RISK_REJECTED` |
| **Portfolio & Metrics** | `PORTFOLIO_UPDATED`, `METRICS_UPDATED` |
| **Health** | `HEALTH_CHECK_PASSED`, `HEALTH_CHECK_FAILED` |
| **Daily Operations** | `DAILY_PNL_RESET`, `DRAWDOWN_LIMIT_HIT`, `KILL_SWITCH_TOGGLED` |

#### Event Payload Contracts

`EventPayload` dataclass defines `required_keys`, `optional_keys`, `notes`, `version` for each event type. The `EVENT_PAYLOADS` dictionary maps every `EventType` to its contract.

#### Typed Event Classes (P5 Stability Engineering)

| Class | Fields | Factory |
|---|---|---|
| `OrderUpdatedEvent` | `order: Order`, `underlying_event: Any` | `from_domain_event(event)` |
| `TradeFilledEvent` | `trade: Trade`, `underlying_event: Any` | `from_domain_event(event)` |
| `TradeAppliedEvent` | `trade: Trade`, `underlying_event: Any` | `from_domain_event(event)` |

All are `@dataclass(frozen=True)` with delegated properties: `event_type`, `event_id`, `correlation_id`

---

### 5.5 Ports / Interfaces

All ports use `@runtime_checkable` Protocol classes for structural subtyping.

| Port | File | Methods |
|---|---|---|
| `OrderTransportPort` | `domain/ports/broker_gateway.py` | `place_order(symbol, exchange, side, quantity, price, order_type, product_type, correlation_id, transport_only) → OrderResponse` |
| `EventPublisher` | `domain/ports/event_publisher.py` | `publish(event) → None`, `subscribe(event_type, handler) → None` |
| `MarginProviderPort` | `domain/ports/margin_provider.py` | `calculate_margin_for_order(order) → Any` |
| `MarketDataPort` | `domain/ports/market_data.py` | `history(symbol, start, end, *, interval, exchange) → HistoricalSeries \| None` |
| `EventMetricsPort` | `domain/ports/observability.py` | `inc(event_type, outcome, by=1) → None`, `snapshot() → dict` |
| `AlertingEnginePort` | `domain/ports/observability.py` | `evaluate() → list[Any]`, `stop() → None` |
| `OmsBacktestAdapterPort` | `domain/ports/oms_backtest_adapter.py` | `open_long(...)`, `close_long(...)`, `modify_order(...)`, `cancel_order(...)`, `get_position(...)`, `get_orders()` |
| `RiskManagerPort` | `domain/ports/risk_manager.py` | `get_status() → dict`, `is_kill_switch_active() → bool`, `check_order(order_request) → Any` |
| `StrategyEvaluator` | `domain/ports/strategy_evaluator.py` | `evaluate_single(candidate, features) → list[SignalDTO]` |
| `FieldMapping` | `domain/entities/order.py` | `map_order_id(d)`, `map_symbol(d)`, `map_exchange(d)`, `map_side(d)`, `map_status(d)`, etc. (11 methods) |

---

### 5.6 Repositories

| Repository | File | Methods |
|---|---|---|
| `OrderRepository` | `domain/repositories/order_repository.py` | `get_orders(*, symbol, status) → list[Order]`, `get_order(order_id) → Order \| None`, `place_order(request) → OrderResponse`, `cancel_order(order_id) → OrderResponse` |
| `PositionRepository` | `domain/repositories/position_repository.py` | `get_positions() → list[Position]` |

---

### 5.7 State Machines

#### Order Status Transitions — `domain/entities/order_lifecycle.py`

```
OPEN ──────────→ PARTIALLY_FILLED ──→ FILLED (terminal)
  │                    │
  ├──→ FILLED          ├──→ FILLED
  ├──→ CANCELLED       ├──→ CANCELLED
  ├──→ REJECTED        └──→ REJECTED
  └──→ EXPIRED

UNKNOWN → {OPEN, REJECTED, CANCELLED}
```

Terminal states: `FILLED`, `CANCELLED`, `REJECTED`, `EXPIRED`

#### Position State Transitions — `domain/entities/position.py`

```
FLAT ──────→ OPEN ──────→ REDUCING ──→ FLAT
  │            │               │
  │            ├──→ CLOSED     ├──→ OPEN
  │            └──→ REVERSED   ├──→ CLOSED
  │                            └──→ REVERSED
  └──→ REVERSED
  
CLOSED → FLAT
REVERSED → {FLAT, OPEN, REDUCING, CLOSED}
```

---

### 5.8 Constants Summary

#### Auth Constants — `domain/constants/auth.py`

| Constant | Value |
|---|---|
| `TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS` | 300.0 |
| `DHAN_TOKEN_REFRESH_BUFFER_SECONDS` | 600.0 |
| `DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS` | 1200 |
| `DHAN_TOKEN_LIFETIME_SECONDS` | 86400 |
| `DHAN_REFRESH_COOLDOWN_SECONDS` | 60 |
| `TOKEN_CLOCK_SKEW_SECONDS` | 30.0 |

#### Risk Constants — `domain/constants/risk.py`

| Constant | Value |
|---|---|
| `RISK_DAILY_LOSS_PERCENT` | 5.0 |
| `RISK_POSITION_PERCENT` | 20.0 |
| `RISK_GROSS_PERCENT` | 100.0 |
| `RISK_LOSS_CIRCUIT_BREAKER_PERCENT` | 2.0 |
| `RISK_LOSS_CB_COOLDOWN_SECONDS` | 1800 |
| `RISK_LOSS_CB_WINDOW_SECONDS` | 86400 |
| `RISK_MARGIN_SAFETY_MULTIPLIER` | 1.2 |
| `PHANTOM_CAPITAL_INR` | 1,000,000 |
| `DHAN_NOTIONAL_WARNING_INR` | 50,000 |

#### Resilience Constants — `domain/constants/resilience.py`

| Constant | Value |
|---|---|
| `MAX_RETRY_DELAY_MS` | 30,000 |
| `RETRY_BASE_DELAY_MS` | 1,000 |
| `MAX_RETRY_ATTEMPTS` | 3 |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 |
| `CIRCUIT_BREAKER_SUCCESS_THRESHOLD` | 3 |
| `CIRCUIT_BREAKER_OPEN_DURATION_MS` | 30,000 |
| `BACKOFF_MULTIPLIER` | 2.0 |
| `BACKOFF_JITTER` | 0.2 |

#### Market Constants — `domain/constants/market.py`

| Constant | Value |
|---|---|
| `DEFAULT_TICK_SIZE` | 0.05 |
| `DEFAULT_EXCHANGE` | `"NSE"` |
| `DEFAULT_DERIVATIVES_EXCHANGE` | `"NFO"` |
| `NSE_OPEN_HOUR_IST / MINUTE` | 9:15 |
| `NSE_CLOSE_HOUR_IST / MINUTE` | 15:30 |
| `MCX_OPEN_HOUR_IST / MINUTE` | 9:00 |
| `MCX_CLOSE_HOUR_IST / MINUTE` | 23:30 |
| `ATR_PERIOD_DEFAULT` | 14 |
| `RSI_PERIOD_DEFAULT` | 14 |
| `SMA_WINDOW_DEFAULT` | 20 |
| `IST_OFFSET` | UTC+5:30 |

#### Timeout Constants — `domain/constants/timeouts.py`

| Constant | Value |
|---|---|
| `DEFAULT_STOP_TIMEOUT_SECONDS` | 5.0 |
| `DEFAULT_HTTP_TIMEOUT_SECONDS` | 15.0 |
| `MIN_SLEEP_SECONDS` | 0.001 |
| `QUOTE_CACHE_TTL_SECONDS` | 60 |
| `HISTORY_CACHE_TTL_SECONDS` | 300 |

#### OMS Constants — `domain/constants/__init__.py`

| Constant | Value |
|---|---|
| `RECONCILIATION_INTERVAL_SECONDS` | 300.0 |
| `DAILY_PNL_POLL_INTERVAL_SECONDS` | 60.0 |
| `DAILY_PNL_ROLLOVER_HOUR_IST` | 0 |
| `PROCESSED_TRADE_RETENTION_SECONDS` | 86,400 |
| `PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS` | 3,600 |
| `BATCH_MAX_WORKERS` | 5 |
| `DEAD_LETTER_QUEUE_MAX_SIZE` | 10,000 |

#### Default Constants — `domain/constants/defaults.py`

| Constant | Value | Env Override |
|---|---|---|
| `RISK_FALLBACK_CAPITAL` | 100,000 | `RISK_FALLBACK_CAPITAL` |
| `PAPER_INITIAL_CAPITAL` | 1,000,000 | `PAPER_INITIAL_CAPITAL` |
| `PAPER_MAX_POSITION_PCT` | 10,000 | `PAPER_MAX_POSITION_PCT` |
| `DEFAULT_LOOKBACK_DAYS` | 90 | — |
| `DEFAULT_TIMEFRAME` | `"1D"` | — |



---

## 6. Event-Driven Framework Details

### 6.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  PRODUCERS                                                       │
│  Broker WebSocket │ OMS │ Trading Orch. │ Scanner │ Lifecycle   │
└──────────┬──────────────────────────────────────────────────────┘
           │ publish(DomainEvent)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  AsyncEventBus (infrastructure/async_event_bus.py)               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Bounded Queue (10,000 events, FIFO)                      │  │
│  │  Critical events (TRADE_APPLIED, TRADE_FILLED,            │  │
│  │  ORDER_PLACED) never dropped — overflow rather than lose  │  │
│  └──────────────────────────┬────────────────────────────────┘  │
│                             │ single worker thread drains       │
│                             ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  EventBus (infrastructure/event_bus/event_bus.py)          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐   │  │
│  │  │ Idempotency  │  │ Event Log    │  │ Dispatch to   │   │  │
│  │  │ Check (LRU)  │  │ (persist)    │  │ Subscribers   │   │  │
│  │  └──────────────┘  └──────────────┘  └───────┬───────┘   │  │
│  └──────────────────────────────────────────────────────────────┘
│                             │ on failure                      │
│                             ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  DeadLetterQueue (bounded FIFO, 10,000 entries)            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  CONSUMERS                                                       │
│  OrderManager │ PositionManager │ MarketBridge │ RiskManager    │
│  Reconciliation │ DlqMonitor │ DailyPnLReset │ Metrics         │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 DomainEvent Structure

**File:** `infrastructure/event_bus/event_bus.py`

```python
@dataclass(frozen=True)
class DomainEvent:
    event_type: str                                    # e.g., "TICK", "TRADE"
    timestamp: datetime                                # Timezone-aware (UTC)
    payload: dict                                      # Event-specific data
    symbol: str | None = None                          # Associated symbol
    source: str | None = None                          # Origin identifier
    event_id: str = uuid.uuid4().hex[:16]              # Unique ID
    correlation_id: str | None = None                  # Auto-injected from context
    sequence_number: int = 0                           # Monotonic counter (P4)
```

**Factory method:** `DomainEvent.now(event_type, payload, symbol=None, source=None, correlation_id=None)`
- Auto-sets `timestamp` to UTC now
- Auto-injects `correlation_id` from `contextvars` if not provided
- Defensive shallow copy of `payload` to prevent handler mutation

### 6.3 Synchronous EventBus

**File:** `infrastructure/event_bus/event_bus.py`

#### Key Design Properties

| Property | Implementation |
|---|---|
| **Thread-safe subscribe** | `threading.Lock` protects subscriber list mutations |
| **Lock-free sequence numbering** | `itertools.count(1)` — atomic under CPython GIL |
| **Snapshot-based dispatch** | Handlers snapshotted before iteration — handler can't corrupt dispatch loop |
| **Mandatory failure observability** | Every handler failure is: (1) logged at WARNING, (2) counted in EventMetrics, (3) pushed to DeadLetterQueue |
| **Idempotency** | Bounded LRU cache tracks processed `event_id` values — prevents duplicate processing |
| **Replay mode** | Disables auto-persistence, preserves original timestamps for deterministic replay |
| **Background alerting** | Optional thread evaluates alert rules periodically |

#### Publish Flow

```
bus.publish(event)
    │
    ├── 1. Prepare event
    │      ├── Inject correlation_id from contextvars (if missing)
    │      └── Assign sequence_number from itertools.count(1)
    │
    ├── 2. Idempotency check
    │      └── Skip if event_id already in _processed_events (bounded LRU)
    │
    ├── 3. Persist to event log
    │      └── event_log.append(event) — crash recovery
    │
    ├── 4. Dispatch to handlers
    │      ├── Snapshot handlers list (under lock)
    │      └── For each handler: handler(event)
    │
    └── 5. Handle failures (per handler)
           ├── Log WARNING with event_type, handler_id, error
           ├── Count in EventMetrics: (event_type, handler_error:<ExceptionType>)
           └── Push to DeadLetterQueue
```

#### Subscribe API

```python
# Returns a token for unsubscribing
token = bus.subscribe("TICK", lambda event: print(event.payload))
token = bus.subscribe(["TICK", "DEPTH"], handler_fn)
bus.unsubscribe(token)
```

### 6.4 AsyncEventBus Adapter

**File:** `infrastructure/async_event_bus.py`

Wraps synchronous `EventBus` with background thread dispatch for high-throughput scenarios.

| Property | Value |
|---|---|
| **Queue** | Bounded `deque` (default 10,000 events) |
| **Backpressure** | When queue full, normal events are dropped; critical events overflow |
| **Critical events** | `TRADE_APPLIED`, `TRADE_FILLED`, `ORDER_PLACED` — never dropped |
| **Worker** | Single background thread preserves FIFO ordering |
| **Batch draining** | Up to 64 events per wake-up cycle |
| **Thread-safe** | `publish()` callable from any thread |

#### Publish Behavior

```
async_bus.publish(event)
    │
    ├── Queue not full → enqueue event
    ├── Queue full + critical event → overflow (expand queue, never drop)
    └── Queue full + normal event → drop + increment dropped counter
```

### 6.5 Dead Letter Queue

**File:** `infrastructure/event_bus/dead_letter_queue.py`

```python
@dataclass(frozen=True)
class DeadLetter:
    event: DomainEvent           # The original event
    handler_id: str              # Which handler failed
    error_type: str              # Exception class name
    error_message: str           # Exception message
    failed_at: datetime          # When it failed
    traceback: str | None        # Full traceback (optional)
```

| Property | Value |
|---|---|
| **Storage** | Bounded `deque(maxlen=10_000)` |
| **Eviction** | Oldest entry dropped when capacity exceeded |
| **Drop callback** | Optional `on_drop` callback for metrics/alerting |
| **Thread-safe** | Protected by `threading.RLock` |
| **Convenience** | `push_failure(event, handler_id, exc, traceback)` builds and pushes |

**DlqMonitorService** (`application/oms/context.py`) drains DLQ during graceful shutdown.

### 6.6 Event Publisher Port

**File:** `domain/ports/event_publisher.py`

```python
@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: Any) -> None: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...
```

Domain services depend on this Protocol — not the concrete `EventBus` — enabling test doubles and alternative implementations.

### 6.7 Event Flow Examples

#### Order Placement Event Chain

```
OrderManager.place_order()
    │
    ├── publishes ORDER_PLACED
    │       payload: {order: Order, correlation_id: str}
    │
    ├── RiskManager.check_order()
    │   ├── publishes RISK_APPROVED    (if approved)
    │   └── publishes RISK_REJECTED    (if rejected)
    │
    ├── Broker submission
    │   └── publishes ORDER_SUBMITTED
    │
    └── Broker fill (async)
        └── publishes TRADE
                │
                ▼
            OrderManager.on_trade()
                ├── publishes ORDER_UPDATED
                └── publishes TRADE_APPLIED (OMS-private)
                        │
                        ▼
                    PositionManager.on_trade_applied()
                        ├── publishes POSITION_OPENED   (FLAT→OPEN)
                        ├── publishes POSITION_CHANGED  (quantity update)
                        └── publishes POSITION_CLOSED   (OPEN→CLOSED)
```

#### Market Data Event Chain

```
Broker WebSocket receives tick
    │
    ├── Broker adapter publishes TICK event
    │       payload: {symbol, ltp, volume, ...}
    │
    ├── MarketBridge subscribes to TICK, QUOTE, DEPTH, TRADE
    │   └── Puts event into asyncio.Queue (drop-oldest policy)
    │       └── Dispatch loop broadcasts to WebSocket clients
    │
    └── Scanner subscribes to TICK
        └── Evaluates scan rules → publishes CANDIDATE_GENERATED
```

### 6.8 Event Log (Crash Recovery)

**File:** `infrastructure/event_log.py`

- Append-only JSONL files stored in `runtime/event-log/` (one file per day: `YYYY-MM-DD.jsonl`)
- Each event serialized as JSON with all fields
- On startup, events can be replayed to restore state
- Replay mode on EventBus disables re-persistence and preserves original timestamps

---

## 7. Dependency Injection & Code Patterns

### 7.1 Service Container (DI)

**File:** `api/deps.py`

#### Immutable ServiceContainer

```python
@dataclass(frozen=True)
class ServiceContainer:
    datalake_gateway: Any = None
    view_manager: Any = None
    data_catalog: Any = None
    event_bus: Any = None
    broker_service: Any = None
    trading_context: Any = None
    risk_manager: Any = None
    order_manager: Any = None
    position_manager: Any = None
    market_data_composer: Any = None
    execution_composer: Any = None
    extra: dict[str, Any] = field(default_factory=dict)
```

**Key design decisions:**
- **Immutable after creation** — prevents race conditions from mutable global dict
- **Populated once at startup** — during FastAPI lifespan event
- **Type-safe** — dataclass instead of raw dict for discoverability
- **OMS readiness check** — `is_oms_ready()` validates all OMS components

#### FastAPI Dependency Functions

```python
def get_container() -> ServiceContainer: ...         # Raises 503 if not initialized
def get_trading_context() -> Any: ...                # Depends(get_container)
def get_order_manager() -> Any: ...                  # Falls back to trading_context.order_manager
def get_position_manager() -> Any: ...               # Falls back to trading_context.position_manager
def get_risk_manager() -> Any: ...                   # Falls back to trading_context.risk_manager
def get_market_data_composer() -> Any: ...           # Returns market_data_composer
def get_execution_composer() -> Any: ...             # Returns execution_composer
def get_datalake_gateway() -> Any: ...               # Returns datalake_gateway
def get_view_manager() -> Any: ...                   # Returns view_manager
def get_broker_service() -> Any: ...                 # Returns broker_service
def get_order_repository() -> Any: ...               # Returns OrderManagerRepository adapter
```

#### Service Initialization

`initialize_all_services()` is called once during FastAPI startup:
1. Extracts OMS components from `TradingContext`
2. Creates immutable `ServiceContainer`
3. Logs missing services with 503 warnings

### 7.2 Runtime Hooks (Factory Registration)

**File:** `domain/runtime_hooks.py`

**Problem:** Domain layer cannot import from infrastructure/application (architecture violation)

**Solution:** Register factory functions at composition root

```python
@dataclass(frozen=True)
class RuntimeHooks:
    oms_backtest_factory: Callable[..., Any] | None = None
    domain_event_factory: Callable[..., Any] | None = None
    trading_context_factory: Callable[..., Any] | None = None

# Registration at startup (api/main.py)
register_oms_backtest_factory(create_oms_backtest_adapter)
register_domain_event_factory(create_domain_event)
register_trading_context_factory(create_trading_context)
```

**Usage in domain code:**
```python
event = create_domain_event(event_type="TICK", payload={"ltp": 100})
```

### 7.3 Design Patterns

#### 7.3.1 Factory Pattern

| Factory | File | Creates |
|---|---|---|
| `create_trading_context()` | `application/oms/factory.py` | `TradingContext` with all OMS components |
| `create_composers_from_infra()` | `application/composer/factory.py` | `(MarketDataComposer, ExecutionComposer)` |
| `AsyncEventBusFactory.create_from_config()` | `infrastructure/event_bus/factory.py` | `(EventBus, config)` |
| `TradingRuntimeFactory` | `runtime/trading_runtime_factory.py` | `Runtime` dataclass (full system) |

#### 7.3.2 Repository Pattern

**Port** (domain layer):
```python
@runtime_checkable
class OrderRepository(Protocol):
    def get_orders(self, *, symbol=None, status=None) -> list[Order]: ...
    def get_order(self, order_id: str) -> Order | None: ...
    def place_order(self, request: OrderRequest) -> OrderResponse: ...
    def cancel_order(self, order_id: str) -> OrderResponse: ...
```

**Adapter** (application layer):
```python
class OrderManagerRepository:
    """Adapts OrderManager to OrderRepository protocol."""
    def __init__(self, order_manager: OrderManager): ...
    def get_orders(self, **kwargs) -> list[Order]: ...
```

**Usage in API:**
```python
@router.get("")
async def get_orders(repo=Depends(get_order_repository)):
    return repo.get_orders(status=status)
```

#### 7.3.3 Strategy Pattern

**BrokerRouter** (`brokers/common/router.py`):
- **Strategy:** `SourceSelectionPolicy` determines broker selection
- **Context:** `BrokerRouter` uses policy to make routing decisions
- **Algorithms:** priority-list, round-robin, quota-aware

```python
router = BrokerRouter(registry=registry, policy=policy)
decision = router.route(RoutingRequest(operation=OperationKind.PLACE_ORDER))
# decision.primary_broker = "dhan"
```

#### 7.3.4 Observer Pattern (Event Bus)

- **Subject:** `EventBus` maintains subscriber list
- **Observers:** Event handlers (`OrderManager`, `PositionManager`, `MarketBridge`, etc.)
- **Notification:** `bus.publish(event)` notifies all subscribers for matching event types

#### 7.3.5 Adapter Pattern

**Broker Adapters** (`brokers/dhan/`, `brokers/upstox/`, `brokers/paper/`):
- Adapt broker-specific APIs to `CommonBrokerGateway` protocol
- Normalize broker DTOs to domain models
- Map broker errors to `TradeXV2Error` hierarchy

**Example:**
```python
class DhanGateway:
    async def place_order(self, request, *, quota):
        dhan_request = self._to_dhan_order(request)      # Domain → Dhan format
        dhan_response = await self._client.place_order(dhan_request)
        return self._to_order_response(dhan_response)    # Dhan → Domain format
```

#### 7.3.6 Composite Pattern

**ExecutionComposer** (`application/composer/execution.py`):
- Composes `BrokerRegistry`, `BrokerRouter`, `QuotaScheduler`
- Provides unified interface for order execution
- Delegates to individual components for routing, quota, and execution

**MarketDataComposer** (`application/composer/market_data.py`):
- Composes `HistoricalDataCoordinator`, `StreamOrchestrator`
- Unified interface for historical and streaming data

#### 7.3.7 Registry Pattern

**BrokerRegistry** (`brokers/common/registry.py`):
- Central registry for broker gateways
- Tracks capabilities, health, stream summaries
- Thread-safe with `threading.RLock`

**ExtensionRegistry** (`brokers/common/extensions/`):
- Registry for broker-specific extensions
- Brokers register extension bundles at bootstrap

#### 7.3.8 State Machine Pattern

**Generic StateMachine** (`infrastructure/state_machine.py`):
```python
sm = StateMachine(transitions=ORDER_STATE_TRANSITIONS, initial=OrderStatus.OPEN)
sm.transition_to(OrderStatus.PARTIALLY_FILLED)  # OK
sm.transition_to(OrderStatus.OPEN)              # Raises IllegalTransitionError
```

Used by: Order lifecycle, Position lifecycle, Scanner lifecycle, Strategy lifecycle

#### 7.3.9 Circuit Breaker Pattern

**Location:** `brokers/common/resilience/circuit_breaker.py`

| State | Behavior |
|---|---|
| **CLOSED** | Normal operation — requests pass through |
| **OPEN** | Broker unavailable — requests fail fast with `CircuitBreakerOpenError` |
| **HALF_OPEN** | Testing recovery — limited requests allowed |

- Opens after N consecutive failures (default: `CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5`)
- Closes after M successful health checks (default: `CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 3`)
- Open duration: `CIRCUIT_BREAKER_OPEN_DURATION_MS = 30,000`

#### 7.3.10 Unit of Work Pattern

**TradingContext** (`application/oms/context.py`):
- Wires together `EventBus`, `OrderManager`, `PositionManager`, `RiskManager`
- Coordinates transaction boundaries
- Manages lifecycle services:
  - `ReconciliationService` — periodic order/position reconciliation
  - `DlqMonitorService` — drains dead-letter queue on shutdown
  - `DailyPnLResetScheduler` — polls for midnight IST rollover

```python
ctx = TradingContext(
    event_bus=event_bus,
    order_manager=order_manager,
    position_manager=position_manager,
    risk_manager=risk_manager,
)
ctx.start()   # Starts background services
ctx.stop()    # Graceful shutdown — drains DLQ, stops reconciliation
```

---

*End of Document*
