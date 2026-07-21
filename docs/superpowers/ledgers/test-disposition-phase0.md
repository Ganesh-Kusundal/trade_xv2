# Test Disposition Ledger (Phase 0)

Generated from `scripts/ci/classify_test_suite.py`. Total files: **887**.

## Summary

| Disposition | Count |
|---|---:|
| KEEP | 568 |
| REWRITE | 259 |
| MOVE_STATIC | 51 |
| MOVE_LAYER | 9 |

## Full ledger

| Path | Layer | Disposition | Smells | Rationale |
|---|---|---|---|---|
| `tests/acceptance/oms/test_broker_fill_acceptance.py` | acceptance | KEEP | — | Behavioral / no smell detected |
| `tests/acceptance/oms/test_paper_fill_acceptance.py` | acceptance | KEEP | — | Behavioral / no smell detected |
| `tests/architecture/regression_invariants/test_golden_dataset.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/regression_invariants/test_memory_leaks.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_api_no_ui_imports.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_application_no_infra_imports.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_broker_data_access_compliance.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_broker_kernel_guardrails.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_broker_routing.py` | architecture | REWRITE | signature | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_broker_session_state_single_source.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_capability_manifest_contract.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_cert_path_unity.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_cert_schema_v2.py` | architecture | REWRITE | mock | Architecture runtime contract |
| `tests/architecture/test_clock_purity.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_composer_bootstrap_compliance.py` | architecture | MOVE_STATIC | ast | Architecture runtime contract |
| `tests/architecture/test_composition_root.py` | architecture | REWRITE | ast | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_concurrency_boundary.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_connect_flow_compliance.py` | architecture | REWRITE | source_read, mock | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_cross_cutting_concerns.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_deepening_enforcement.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_dependency_graph_sync.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_deploy_profile_auth_unbypassable.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_domain_bar_types.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_isolation.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_market_types.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_no_broker_imports.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_no_orchestration_imports.py` | architecture | MOVE_STATIC | ast, source_read | Architecture runtime contract |
| `tests/architecture/test_domain_no_pandas_import.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_no_tradex_imports.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_ports_forbid_tradex_imports.py` | architecture | REWRITE | ast, source_read, caplog | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_domain_purity.py` | architecture | MOVE_STATIC | ast, source_read | Architecture runtime contract |
| `tests/architecture/test_domain_single_source.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_domain_value_object_purity.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_duckdb_single_connection_source.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_eng004_auth_default.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_exception_hierarchy_unified.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_execution_target_resolver.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_factory_uses_canonical_paths.py` | architecture | MOVE_STATIC | ast | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_fail_closed_capital_paths.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_flow_contracts.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_gateway_abc_compliance.py` | architecture | REWRITE | ast, source_read, signature | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_gateway_signatures.py` | architecture | REWRITE | signature | Architecture runtime contract |
| `tests/architecture/test_gateway_surface_freeze.py` | architecture | REWRITE | — | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_import_direction_and_layering.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_imports.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_metrics_auth_profile_scoped.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_module_boundaries_and_decomposition.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_mypy_strict_allowlist.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_no_broker_string_branching.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_no_duplicate_error_hierarchies.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_no_getattr_reexport.py` | architecture | MOVE_STATIC | source_read | Architecture runtime contract |
| `tests/architecture/test_no_interface_broker_imports.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_no_legacy_broker_aliases.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_no_market_data_gateway_alias.py` | architecture | MOVE_STATIC | source_read | Architecture runtime contract |
| `tests/architecture/test_no_private_reachthrough.py` | architecture | MOVE_STATIC | private | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_no_scattered_dotenv.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_no_security_id_leak.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_no_shadow_broker_modules.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_no_tradex_in_application.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_oms_no_broker_name_branching.py` | architecture | MOVE_STATIC | ast | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_order_placement_port.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_order_placement_spine.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_order_port_services.py` | architecture | REWRITE | mock | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_paper_oms_boundary.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_parity_gate_unbypassable.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_place_order_path_inventory.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_platform_ops_unity.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_production_code_fitness_rules.py` | architecture | MOVE_STATIC | ast | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_production_fail_open_unbypassable.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_public_sdk_surface_invariants.py` | architecture | MOVE_STATIC | source_read | Architecture runtime contract |
| `tests/architecture/test_research_mode_gating.py` | architecture | REWRITE | signature | Architecture runtime contract |
| `tests/architecture/test_service_registry.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_shadow_parity_gate.py` | architecture | MOVE_STATIC | source_read, mock | Architecture runtime contract |
| `tests/architecture/test_single_bus.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_single_config.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_single_idempotency.py` | architecture | REWRITE | ast, source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_stream_oms_lock_discipline.py` | architecture | REWRITE | source_read | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_streaming_gateway_port_conformance.py` | architecture | REWRITE | — | Real contract; replace source substring with behavioral assertion |
| `tests/architecture/test_system_invariants.py` | architecture | KEEP | — | Architecture runtime contract |
| `tests/architecture/test_test_suite_uses_behavioral_names.py` | architecture | MOVE_STATIC | — | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_tick_authority.py` | architecture | REWRITE | mock | Architecture runtime contract |
| `tests/architecture/test_ui_broker_ops_delegation.py` | architecture | MOVE_STATIC | source_read, private | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_ui_no_concrete_broker_imports.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_wire_boundary.py` | architecture | MOVE_STATIC | ast, source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/architecture/test_workflow_paths.py` | architecture | MOVE_STATIC | source_read | AST/grep/import ratchet → import-linter / CI script |
| `tests/chaos/test_broker_disconnect.py` | chaos | REWRITE | mock | Smells: mock |
| `tests/chaos/test_cleanup_phantom_dirs.py` | chaos | KEEP | — | Behavioral / no smell detected |
| `tests/chaos/test_concurrent_failures.py` | chaos | KEEP | — | Behavioral / no smell detected |
| `tests/chaos/test_data_corruption.py` | chaos | REWRITE | mock | Smells: mock |
| `tests/chaos/test_dlq_scenarios.py` | chaos | KEEP | — | Behavioral / no smell detected |
| `tests/chaos/test_event_bus_replay_api.py` | chaos | REWRITE | ast, private | Smells: ast, private |
| `tests/chaos/test_failover.py` | chaos | REWRITE | mock | Smells: mock |
| `tests/chaos/test_failure_modes.py` | chaos | REWRITE | mock | Smells: mock |
| `tests/chaos/test_network_partitions.py` | chaos | REWRITE | mock | Smells: mock |
| `tests/chaos/test_oms_lock_survives_concurrent_fills.py` | chaos | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/chaos/test_production_scenarios.py` | chaos | KEEP | — | Behavioral / no smell detected |
| `tests/chaos/test_rate_limit_exhaustion.py` | chaos | KEEP | — | Behavioral / no smell detected |
| `tests/chaos/test_reconciliation_failures.py` | chaos | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/chaos/test_recovery_certification.py` | chaos | KEEP | source_read | Money-safety / contract / regression preserve list |
| `tests/component/application/trading/test_orchestrator_execution_plan.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/brokers/test_broker_lifecycle_events.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/brokers/test_brokersession_federation.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/brokers/test_instrument_service_boundary.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/composer/test_execution_composer.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/composer/test_factory.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/execution/test_backtest_clock_purity.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/execution/test_execution_mode_adapter.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/execution/test_execution_mode_oms_parity.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/execution/test_execution_target_resolver.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/execution/test_gateway_submit.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/execution/test_parity_characterization.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_capital_provider_fail_closed.py` | component | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/component/oms/test_composition.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_concurrent_rapid_fills.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_correlation_id_warning.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_crash_replay_positions.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_daily_pnl_feed_wiring.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_extended_order_risk.py` | component | REWRITE | private, mock | Smells: private, mock |
| `tests/component/oms/test_extended_order_service_registry.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_graceful_shutdown.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_live_path_risk_gate_and_capital.py` | component | KEEP | mock, signature | Money-safety / contract / regression preserve list |
| `tests/component/oms/test_loss_circuit_breaker.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_money_safety_invariants.py` | component | KEEP | ast | Money-safety / contract / regression preserve list |
| `tests/component/oms/test_oms_safety.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_oms_writer_lock.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_audit_logger.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_blocked_error.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_command_mapper.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_lifecycle_end_to_end.py` | component | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/component/oms/test_order_manager_core_behavior.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_path_parity.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_order_position_updater.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_order_state_transitions.py` | component | REWRITE | mock, caplog | Smells: mock, caplog |
| `tests/component/oms/test_order_state_validator.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_partial_fill_lifecycle.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_position_state_machine_enforcement.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_process_oms_book_is_shared.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_processed_trade_repository_singleton.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_reconciliation_attach.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_reconciliation_gate.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_reconciliation_service.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_risk_effective_notional.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_risk_manager_concurrency.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_risk_manager_margin.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_risk_manager_risk_profile.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_risk_pending_reservation.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_session_bridge.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_sqlite_order_store_restart.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_tick_validation.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/oms/test_trade_idempotency.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/oms/test_trade_ledger_apply_then_mark.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/portfolio/test_portfolio_service.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/runtime/test_broker_discovery.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/runtime/test_production_config.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/runtime/test_trading_runtime_factory.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/services/test_production_readiness_fail_closed.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/test_broker_router_selects_healthy_source.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/test_connection_pool_limits_concurrency.py` | component | REWRITE | mock, caplog | Smells: mock, caplog |
| `tests/component/test_download_engine_persists_history.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/test_event_log_buffers_and_replays.py` | component | REWRITE | mock, caplog | Smells: mock, caplog |
| `tests/component/test_gap_reconciler_fills_missing_bars.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/test_instrument_registry_lookup.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/test_md5_cache_can_be_disabled.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/test_replay_orchestrator_advances_bars.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/test_scanner_runner_emits_candidates.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/trading/test_multi_strategy_runtime.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/trading/test_orchestrator_kill_switch_port.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/trading/test_trading_orchestrator_lifecycle.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/trading/test_trading_orchestrator_sizing.py` | component | REWRITE | mock | Smells: mock |
| `tests/component/ui/test_broker_infrastructure.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_broker_service_concurrency.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_cli_endpoint_matrix.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_command_registry.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_http_observability_headers.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_oms_service.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/component/ui/test_ui_services_parity.py` | component | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/scenarios/test_live_l3_optional.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/scenarios/test_object_model_pyramid.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/stability/test_event_bus_idempotency.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/stability/test_metrics.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/stability/test_structured_logging.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/stability/test_tracing.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/stability/test_typed_events_and_idempotency.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/stress/test_oms_stress.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_analytics_session_smoke.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_automation_w3.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_backtest_session_history.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_circuit_breaker_recovery_flow.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_cli_real_data.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_complete_trading_flow.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_derivatives_greeks.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_derivatives_object_model.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_initialization_flow.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_lock_contention.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_market_access.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_market_data_to_order_flow.py` | e2e | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/e2e/test_object_model.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_order_lifecycle.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_replay_backtest_flow.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_resource_leaks.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_sandbox_product_orders.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_sandbox_real_broker.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_scanner_to_order_flow.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_signal_to_reconciliation_flow.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_token_refresh_and_order_retry_flow.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_trading_flow.py` | e2e | KEEP | — | Behavioral / no smell detected |
| `tests/e2e/test_trading_object_model.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_trading_w2.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/e2e/test_websocket_to_pnl_flow.py` | e2e | REWRITE | mock | Smells: mock |
| `tests/fixtures/test_fake_broker_gateway.py` | fixtures | KEEP | — | Behavioral / no smell detected |
| `tests/integration/analytics/test_oms_slippage_once.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/analytics/test_replay_pending_signal_f2e.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/routers/test_orders.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_analytics_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_api_bootstrap_wiring.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_api_config.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_audit_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_auth.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_auth_default_mode.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_auth_modes.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_backtest_comparison.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_backtest_endpoints.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_cache_headers.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_candle_endpoint_parity.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_composer_di_registration.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_contract.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_extended_order_routes.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_feed_wiring.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_freshness.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_health.py` | integration | REWRITE | caplog | Smells: caplog |
| `tests/integration/api/test_health_symbols.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_live_extended_account.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_live_extended_orders.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_live_headers.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_live_health.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_live_market_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_live_serialize.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_market_analytics.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_market_bridge.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_market_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_oms_lifecycle.py` | integration | REWRITE | mock, caplog | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_openapi_contract.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_options_bid_ask.py` | integration | REWRITE | signature | Smells: signature |
| `tests/integration/api/test_options_replay.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_order_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_order_validation.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_performance.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_portfolio_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_portfolio_integration.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_portfolio_orders.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_rate_limit.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_rate_limit_middleware.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_replay_endpoints.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_scanner_endpoints.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_scanner_run.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_service_container.py` | integration | REWRITE | mock, caplog | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_square_off.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_upstox_webhook.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/api/test_vectorized_candles.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_ws_market.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/api/test_ws_replay.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/certification/test_e2e_paper_trading_os.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/dhan/contract/test_broker_contract.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/dhan/contract/test_market_coverage.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/regression/test_coverage_manifest.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/dhan/regression/test_e2e_smoke.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_endpoint_latency.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_error_paths.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_batch_market_data.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_derivatives_chain.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_instruments.py` | integration | MOVE_LAYER | ast | No source AST in integration |
| `tests/integration/brokers/dhan/test_live_market_data_rest.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_observability.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_options.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_order_lifecycle.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_portfolio.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_quotes.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_read_surface_suite.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/dhan/test_live_streaming.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_live_validation.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/brokers/dhan/test_live_websocket.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/brokers/dhan/test_schema_enforcement.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_symbol_mapping_live.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/dhan/test_ws_parity.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/brokers/test_certification_live_probes.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/test_common_market_data_contracts.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_dhan_gateway_idempotency_and_stream.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_dhan_market_feed_reconnect.py` | integration | MOVE_LAYER | ast, signature | No source AST in integration |
| `tests/integration/brokers/test_dhan_timestamps_are_exchange_aligned.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_live_actionable_gate_wiring.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/brokers/test_live_candles_normalize_consistently.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_paper_limit_fill_on_tick.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_upstox_data_provider_subscribe.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/test_upstox_extended_capabilities.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/brokers/test_upstox_gateway_contracts.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/contract/test_broker_contract.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/upstox/contract/test_market_coverage.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/contract/test_upstox_contract.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/upstox/regression/test_coverage_manifest.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/upstox/regression/test_e2e_smoke.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_endpoint_latency.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_error_paths.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_batch_market_data.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_derivatives_chain.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_extended.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_instruments.py` | integration | MOVE_LAYER | ast | No source AST in integration |
| `tests/integration/brokers/upstox/test_live_market_data_rest.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_options.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_order_lifecycle.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_portfolio.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_quotes.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_read_surface_suite.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/brokers/upstox/test_live_streaming.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_live_websocket.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_schema_enforcement.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_symbol_mapping_live.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/brokers/upstox/test_ws_parity.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/capability/test_api_route_manifest.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/capability/test_audit_broker_methods.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/capability/test_capability_certification.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/capability/test_cli_rest_parity.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/capability/test_extended_capabilities_registered.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/capability/test_upstox_future_chain.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/contract/test_broker_gateway_contract.py` | integration | REWRITE | signature | Smells: signature |
| `tests/integration/contract/test_protocol_implementations.py` | integration | REWRITE | signature | Smells: signature |
| `tests/integration/datalake/test_live_bar_sink.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/performance/test_benchmarks.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/performance/test_data_performance.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/quant/test_analytics_entry_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_cross_broker_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_live_backtest_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_paper_projection_parity.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_paper_replay_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_projection_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_quant_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_strategy_evaluator_bridge.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/quant/test_views_pipeline_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/runtime/test_paper_oms_target.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/scripts/test_broker_connections.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/scripts/test_cli_speed.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/scripts/test_options_contracts.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/scripts/test_options_gateway.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/scripts/test_upstox_historical_fix.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_auth_failure_paths.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_auth_totp_live.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_cancel_verification.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/test_config_validation_integration.py` | integration | REWRITE | caplog | Smells: caplog |
| `tests/integration/test_cross_broker_parity.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_dhan_api_live_readonly.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_dhan_websocket_reconnect_and_payloads.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_event_bus_flow.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/test_event_log_replay.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_event_replay_determinism.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/test_execution_parity.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/test_gateway_contract.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_idempotent_place.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/test_instrument_resolution_end_to_end.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_kill_switch_atomic_flip.py` | integration | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/integration/test_oms_broker_integration.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_oms_event_dedup.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_parity_gate.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/test_processed_trade_repository_crash_recovery.py` | integration | MOVE_LAYER | source_read | No source AST in integration |
| `tests/integration/test_reconcile_heals_phantom.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_reconcile_in_engine.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_replay_determinism.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_resilience_composition.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_restart_trade_replay.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_risk_deny_never_hits_venue.py` | integration | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/integration/test_runtime_validation_audit.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_trading_runtime_orchestrator.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_upstox_gateway_integration.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_upstox_market_data.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_upstox_order_lifecycle.py` | integration | REWRITE | mock | De-mock money path; use paper/recording fakes |
| `tests/integration/test_upstox_portfolio_oms.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_view_manager_composition.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/integration/test_websocket_reconnect_failure.py` | integration | KEEP | — | Behavioral / no smell detected |
| `tests/performance/test_critical_paths.py` | performance | REWRITE | private | Smells: private |
| `tests/unit/analytics/backtest/test_comparator.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/backtest/test_optimizer.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/backtest/test_research_mode.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/indicators/test_halftrend.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/indicators/test_swing_detection.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/intraday/test_afternoon_expansion.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/pipeline/test_candlestick_pattern_feature.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/ranking/test_ranking_integration.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/replay/test_commission_model.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/replay/test_fill_model.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/replay/test_pnl_precision.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/replay/test_replay_memory.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/replay/test_slippage_model.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/analytics/reports/test_reports_integration.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/scanner/test_candidate_identity.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/analytics/scanner/test_determinism.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/scanner/test_pattern_engine.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/scanner/test_scanner_performance.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/stocks/test_find_levels.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/strategy/test_strategy_self_check.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_backtest.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_breadth.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_core.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_deep_dive.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_feature_indicator_parity.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_feature_pipeline_fail_closed.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_features.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_greeks.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_indicators.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_market_structure.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_options.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_orderflow.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_paper.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/analytics/test_paper_multi_symbol.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/analytics/test_pipeline.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_providers.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_ranking_determinism.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_replay.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/analytics/test_replay_equity_costs.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_reports.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_scanner.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_sector.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_shared_trade_types.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_stocks.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_strategy.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_strategy_registry_self_check.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_visualizations.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_volatility.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/test_volume_profile.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/views/test_view_determinism.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/views/test_views.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/analytics/walk_forward/test_walk_forward.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/execution/test_execution_engine.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/oms/test_daily_pnl_reset_scheduler_fires_at_virtual_time.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_daily_pnl_self_heal.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_fill_reducer.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_ledger_shadow.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/oms/test_live_order_authority.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_modify_fail_closed.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/oms/test_risk_double_count.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_risk_fail_closed.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/oms/test_risk_policy_chain.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_throttler.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/oms/test_trading_state.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/portfolio/test_active_session_market_mode.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/portfolio/test_portfolio_context.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/application/services/test_api_readiness.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/streaming/test_orchestrator_gap_inject.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/streaming/test_streaming_consumer_uses_virtual_clock.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/test_options_capability.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/application/test_production_readiness_security.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/application/trading/test_signal_coordinator.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/brokers/certification/test_certification_paper.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/certification/test_cli_smoke.py` | unit | KEEP | caplog | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/certification/test_live_probes.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/certification/test_market_hours.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/cli/test_broker_commands.py` | unit | KEEP | caplog | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/cli/test_cli_history_batch.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/cli/test_cli_render.py` | unit | KEEP | caplog | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/cli/test_cli_shell.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/cli/test_preferences.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/cli/test_shell_nav.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/cli/test_shell_ui.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/contracts/test_common_broker_gateway.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/common/test_acl.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/common/test_async_compat.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_audit.py` | unit | KEEP | caplog | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_audit_trail_completeness.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_batch_quote_coordinator.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_capabilities.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_capabilities_validator_enforce.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_capabilities_validator_fields.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_e2e_order_lifecycle.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_event_bus.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_event_bus_compatibility_shims.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_event_log.py` | unit | MOVE_STATIC | source_read, mock, caplog | Broker source hygiene → CI |
| `tests/unit/brokers/common/test_extensions_registry.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_gateway_contract_integration.py` | unit | REWRITE | mock, signature | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_gateway_error_surface_contracts.py` | unit | MOVE_STATIC | ast, source_read, mock | Broker source hygiene → CI |
| `tests/unit/brokers/common/test_gateway_errors.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_historical_coordinator.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_historical_gap_check.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_intelligent_market_gateway.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_logging_redaction.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_margin_parse.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_market_data_gateway_adapter.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_provenance_ledger.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_provider_port_contracts.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_quota_scheduler.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_quota_scheduler_integration.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_quote_volume_delta.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_recon_local.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_registry_router.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_router_policy_integration.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_status_mapping.py` | unit | KEEP | mock | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/common/test_stream_orchestrator.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_tick_handling.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/common/test_token_lifecycle_events.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_transport_policy.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_untested_event_types.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/common/test_wire_base.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/dhan/regression/test_depth_merge_and_rate_limit_invariants.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_alerts_adapter.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_cache_refresh.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_cancel_all_errors.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_chaos.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_conditional_triggers.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_config.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_connection.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_convert_position.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_data_provider_subscribe.py` | unit | REWRITE | private, mock, caplog | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_depth_200_websocket.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_depth_20_websocket.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_depth_feeds.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_dhan_bus_golden.py` | unit | MOVE_STATIC | source_read, mock | Broker source hygiene → CI |
| `tests/unit/brokers/dhan/test_domain.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_drift_repair.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_edge_cases.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_edis.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_exit_all.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_extended_order_gate.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_factory.py` | unit | MOVE_STATIC | source_read | Broker source hygiene → CI |
| `tests/unit/brokers/dhan/test_factory_auth.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_factory_resilience_wiring.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_factory_websocket_wiring.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_forever_orders.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_futures.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_gateway.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_gateway_get_order.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_gateway_place_order_payload.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_historical.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_http_client.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_http_client_circuit_breaker_split.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_instrument_search_boundary.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_ip_management.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_ledger.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_loader_cache_path.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_margin_adapter.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_market_data.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_market_feed_connection_race.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_market_feed_degraded.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_options.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_order_canceller_post_cancel.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_order_factory_dhan_resolver.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_order_payload_wire_price.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_order_placement_oms_guard.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_order_stream_exchange_mapping.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_orders.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_orders_idempotency.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_pnl_exit.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_portfolio.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_publish_depth_strict.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_publish_tick_strict.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_real_websocket_payloads.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_reconciliation.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_reconnecting_service.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_resolver.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_segments.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_segments_sdk_constants.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_settings.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_stream_depth_facade.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_stream_order_wire.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_super_orders.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_symbol_mapping.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_token_bootstrap_policy.py` | unit | MOVE_STATIC | source_read, mock | Broker source hygiene → CI |
| `tests/unit/brokers/dhan/test_token_broadcast.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_token_http_ws_sync.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_token_scheduler.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_token_scheduler_lifecycle.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_transform_quote_exchange_timestamp.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_transport.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_user_profile.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_validity_wire_values.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_websocket.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/dhan/test_websocket_feed_lifecycle_invariants.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_websocket_managed_service.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_websocket_reconnect_recovery.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_websocket_reconnection.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_websocket_thread_safety.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/dhan/test_write_path_unaffected_by_read_circuit_open.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/diagnostics/test_doctor_schema.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/paper/contract/test_paper_contract.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/paper/contract/test_paper_market_coverage.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/brokers/paper/test_data_provider_history.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/paper/test_paper.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/paper/test_paper_orders_concurrency.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/paper/test_paper_reject_success.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/services/test_dhan_wire_date_window.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/services/test_live_actionable_gate.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/services/test_pipeline_wiring.py` | unit | KEEP | signature | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/test_capability_exposure.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/test_capability_matrix.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/test_data_provider_protocol.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/test_disclosed_quantity.py` | unit | KEEP | signature | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/test_get_order_direct_lookup.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/test_idempotency_ambiguous.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/test_token_path.py` | unit | MOVE_STATIC | source_read | Broker source hygiene → CI |
| `tests/unit/brokers/test_wire_adapters.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_adapter_edge_case_contracts.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_adapter_failures.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_adapters_tick_translator.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_broker_bundle_split.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_capabilities_wiring.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_cb_4xx.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_context.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_data_provider_subscribe.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_domain_mapper.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_exceptions.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_exchange_from_wire.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_exit_all_gate.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_extended_lazy_load.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_factory_connection_reuse.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_factory_totp_scheduler.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_gateway_history_capability.py` | unit | REWRITE | mock, caplog | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_gateway_order_placement.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_gateway_stream.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_get_order_fallback.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_gtt_adapter.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_holders.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_http_client.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_instrument_loader.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_jwt_expiry.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_loader_pickle_security.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_login.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_market_data_event_bus.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_market_feed_degraded.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_market_quote_batch.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_news.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_oauth_client.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_order_command_adapter.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_order_command_idempotency.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_order_query_adapter.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_pkce.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_price_parser.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_reconciliation_engine.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_reconciliation_signature.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_redirect_server.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_segment_mapper.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_settings_loader.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_stream_depth_facade.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_stream_manager_tick_routing.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_token_expiry.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_token_manager.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_token_refresh_concurrency.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_totp_bootstrap.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_totp_client.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_totp_scheduler.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_trade_pnl.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_upstox_bus_golden.py` | unit | MOVE_STATIC | source_read, mock | Broker source hygiene → CI |
| `tests/unit/brokers/upstox/test_upstox_resolver.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_url_resolver.py` | unit | KEEP | — | Broker contract / golden / ACL behavioral |
| `tests/unit/brokers/upstox/test_v3_decoder.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_websocket_lifecycle.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_websocket_reconnect_recovery.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_websocket_safety.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_websocket_stream_lifecycle_invariants.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/brokers/upstox/test_wire_is_connected.py` | unit | REWRITE | mock | Assert wire→domain observables via public gateway/bus |
| `tests/unit/config/test_config.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/config/test_profiles.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/config/test_validator.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/mcp/test_tools.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_analytics_provider.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_atomic_io.py` | unit | REWRITE | source_read, mock | Smells: source_read, mock |
| `tests/unit/datalake/test_broker_selection.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_canonical_schema_unit.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_catalog.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_catalog_schema_version_applied.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_converter.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_corporate_actions.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_data_equivalence.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_duckdb_e2e.py` | unit | REWRITE | private | Smells: private |
| `tests/unit/datalake/test_duckdb_pool_concurrency.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_exchange_registry.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/datalake/test_exchange_registry_thread_safety.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_features.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_fixes.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_gateway_batch.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/datalake/test_health_check.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_ingestion_normalize.py` | unit | REWRITE | caplog | Smells: caplog |
| `tests/unit/datalake/test_integration.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_journal.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_loader_merge.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_monitor.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_normalize.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/datalake/test_normalize_symbol_canonical.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_option_format.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_option_future_chain_lake.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_options_analytics.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_options_greeks.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_parquet_store.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_paths.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_perf_ltp_quote.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/datalake/test_pit_joins.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_quality.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_quality_universe.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_research.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_research_dataset.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_retry.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_scan_store.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_schema.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_schema_evolves_idempotently.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_support_resistance.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_symbols.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_update_env_token.py` | unit | REWRITE | source_read, mock | Smells: source_read, mock |
| `tests/unit/datalake/test_validation.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/datalake/test_vwap.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/domain/analytics/test_analytics.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/analytics/test_statistics.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/capabilities/test_market_surface.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/events/test_typed_events.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/futures/test_future.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/indicators/test_patterns.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/instruments/test_instrument.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/instruments/test_instrument_factory.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/market/test_exchange_session.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/markets/test_aggregates_behavior.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/markets/test_dhan_adapter.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/markets/test_indicators_behavior.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/markets/test_platform_api.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/options/test_option_chain.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/options_facade/test_chain_normalizer.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/orders/test_execution_plan_signal_mapping.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/orders/test_requests_slicing.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/orders/test_sizing_methods.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_broker_id.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_broker_session_state.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_clock_port.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_data_provider.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/ports/test_exchange_ports.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_execution_context.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/ports/test_execution_provider.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/primitives/test_time_service.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/primitives/test_value_objects.py` | unit | MOVE_STATIC | source_read | Source scan belongs in CI/architecture |
| `tests/unit/domain/quotes/test_quote_stream.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/sessions/test_trading_session.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_asset_kind_and_types.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_bounded_cache.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_broker_adapter_protocol.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_broker_facade_extensions.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_broker_transport_contract.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_chain_stamp_and_derivatives.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_clock_purity.py` | unit | MOVE_STATIC | source_read | Source scan belongs in CI/architecture |
| `tests/unit/domain/test_constants_facade.py` | unit | MOVE_STATIC | ast | Source scan belongs in CI/architecture |
| `tests/unit/domain/test_display_names.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_domain_events_are_immutable.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_domain_immutable.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_domain_ports.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_entities_contract.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_enums.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_event_hooks.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_event_types.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_exception_hierarchy.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_exchange_adapter.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_exchange_id_enum.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_exchange_segments.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_execution.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_future_chain_aggregate.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_historical_bar_factories.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_historical_bar_ingress.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_identity_coercion.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_instrument.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_instrument_history_and_buy.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_instrument_id.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_instrument_id_format.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_instrument_identity.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_instrument_resolver_strikes.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_invoke_place_order_disclosed.py` | unit | REWRITE | mock | Use public domain API + real objects |
| `tests/unit/domain/test_ledger_recovery.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_market_entities.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_market_surface_integration.py` | unit | KEEP | signature | Domain behavioral / invariant test |
| `tests/unit/domain/test_notional_and_position_multiplier.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_order_fsm_enforcement.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_order_money_helpers.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_parsing.py` | unit | KEEP | — | Money-safety / contract / regression preserve list |
| `tests/unit/domain/test_portfolio.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_portfolio_projection.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_position_aggregate.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_price_utils.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_provenance_historical_stream.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_provider_contract.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_provider_resolution.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_reconciliation_engine_economic.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_requests.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_resolver_and_connect_error.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_result.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_risk_policy.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_risk_profile.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_segment_registry.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_signal_dto_to_intent.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_simulation_fill_pipeline.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_status_mapper.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_status_mapper_contract.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_strike_selection_and_batch.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_subscription.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_symbols.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_trading_costs.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/domain/test_universe.py` | unit | KEEP | — | Domain behavioral / invariant test |
| `tests/unit/infrastructure/auth/test_auth_metrics.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/infrastructure/auth/test_credential_resolver.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/auth/test_credential_validator_upstox_files.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/auth/test_environment_bootstrap.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/auth/test_token_ensure.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/infrastructure/auth/test_token_policy.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/auth/test_totp_cooldown.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/connection/test_authenticated_readiness.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/infrastructure/event_bus/test_async_event_bus_priority.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/event_bus/test_event_bus_lifecycle.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/event_bus/test_persistent_dead_letter_queue.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/event_bus/test_processed_trade_crash_recovery.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/infrastructure/lifecycle/test_lifecycle.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/observability/test_alerting.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/infrastructure/observability/test_alerting_service.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/infrastructure/observability/test_http_observability_server.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/observability/test_http_server.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/observability/test_tracing_emitted.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/persistence/test_sqlite_execution_ledger.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/providers/test_broker_data_provider_depth.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_backoff.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_broker_health_monitor.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_circuit_breaker.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_endpoint_rate_limiter.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_multi_bucket_rate_limiter.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_retry.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/resilience/test_single_authority.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/infrastructure/resilience/test_token_bucket_rate_limiter.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/security/test_secret_manager.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/infrastructure/test_audit.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_correlation_async.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_duckdb_pool.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_event_bus_lock_sharding.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_global_exception_handler.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_idempotency_claim.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_infrastructure_smoke.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_opentelemetry_setup.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/infrastructure/test_resource_manager.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_session_recorder.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/infrastructure/test_time_service.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/infrastructure/test_time_service_unified.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/api/test_feed_wiring.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/api/test_order_cancel_modify.py` | unit | REWRITE | source_read, mock | Smells: source_read, mock |
| `tests/unit/interface/api/test_require_live_broker.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/ui/doctor/test_auth_doctor.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_analytics_commands.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_argparse_helpers.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_auth_live_probe_doctor.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_broker_not_ready.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_broker_ops.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/ui/test_broker_registry.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_broker_service_auth_readiness.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_broker_service_lifecycle.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_commands.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/interface/ui/test_doctor_commands.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_doctor_orchestrator.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_doctor_renderer.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/ui/test_doctor_strategies.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_extended_commands.py` | unit | REWRITE | source_read | Smells: source_read |
| `tests/unit/interface/ui/test_ist_time_display.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/ui/test_market_commands.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_oms_modify.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_oms_setup_persistence.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_order_composition.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_order_placement.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_renderers.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/interface/ui/test_risk_controls.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_timeout_retry_error.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_validate_commands.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/interface/ui/test_views_journal_commands.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/market_data/test_market_surface.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/property/test_domain_properties.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/property/test_market_data_properties.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/property/test_order_properties.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/property/test_property_based.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/runtime/test_factory.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/runtime/test_ledger_policy.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/runtime/test_parity_gate.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/runtime/test_quote_fail_closed.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/runtime/test_resilience_config.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/security/test_security_controls.py` | unit | REWRITE | ast, source_read, mock | Smells: ast, source_read, mock |
| `tests/unit/security/test_sql_injection_is_rejected.py` | unit | REWRITE | ast | Smells: ast |
| `tests/unit/security/test_ssl_session_is_hardened.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/security/test_token_expiry_is_enforced.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/security/test_webhook_auth.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/test_config_schema.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/test_domain_port_contracts.py` | unit | REWRITE | signature | Smells: signature |
| `tests/unit/test_no_module_getattr_reexports.py` | unit | REWRITE | ast, source_read | Smells: ast, source_read |
| `tests/unit/test_oms_structure.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/test_tradex_connect_factory.py` | unit | REWRITE | mock | Smells: mock |
| `tests/unit/tradex/test_cli.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/tradex/test_cli_config.py` | unit | KEEP | — | Behavioral / no smell detected |
| `tests/unit/tradex/test_open_session_factory.py` | unit | REWRITE | mock | Smells: mock |
