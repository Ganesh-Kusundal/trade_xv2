# Testing Dependency Graph

## Test Module Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                    SHARED DEPENDENCIES                      │
├─────────────────────────────────────────────────────────────┤
│ fake_http_client (conftest.py:159-161)                      │
│ market_is_open (conftest.py:66-82)                          │
│ live_credentials (conftest.py:84-107)                       │
│ upstox_credentials (conftest.py:110-133)                    │
│ dhanhq_sdk_aliases (conftest.py:14-83)                       │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                  UNIT TEST DEPENDENCIES                      │
├─────────────────────────────────────────────────────────────┤
│ brokers.dhan.tests.unit/                                   │
│ ├── test_architecture_regression.py                        │
│ ├── test_alerts_adapter.py                                 │
│ ├── test_cache_refresh.py                                  │
│ ├── test_chaos.py                                          │
│ ├── test_conditional_triggers.py                          │
│ ├── test_connection.py                                    │
│ ├── test_depth_20_websocket.py                            │
│ ├── test_depth_200_websocket.py                           │
│ ├── test_depth_feeds.py                                    │
│ ├── test_domain.py                                         │
│ ├── test_edge_cases.py                                     │
│ ├── test_edis.py                                           │
│ ├── test_exit_all.py                                       │
│ ├── test_factory.py                                        │
│ ├── test_factory_auth.py                                   │
│ ├── test_futures.py                                       │
│ ├── test_gateway.py                                        │
│ ├── test_historical.py                                    │
│ ├── test_http_client.py                                    │
│ ├── test_http_client_circuit_breaker_split.py               │
│ ├── test_ip_management.py                                  │
│ ├── test_ledger.py                                          │
│ ├── test_loader_cache_path.py                             │
│ ├── test_margin_adapter.py                                 │
│ ├── test_market_data.py                                    │
│ ├── test_orders.py                                         │
│ ├── test_orders_idempotency.py                            │
│ ├── test_options.py                                        │
│ ├── test_portfolio.py                                      │
│ ├── test_reconciliation.py                                 │
│ ├── test_reconnecting_service.py                          │
│ ├── test_real_websocket_payloads.py                       │
│ ├── test_resolver.py                                       │
│ ├── test_segments.py                                       │
│ ├── test_settings.py                                       │
│ ├── test_super_orders.py                                   │
│ ├── test_symbol_mapping.py                                 │
│ ├── test_token_broadcast.py                                │
│ ├── test_token_scheduler.py                                │
│ ├── test_token_scheduler_lifecycle.py                      │
│ ├── test_websocket.py                                      │
│ ├── test_websocket_managed_service.py                      │
│ ├── test_websocket_reconnect_recovery.py                   │
│ ├── test_websocket_thread_safety.py                       │
│ ├── test_websocket_token.py                                │
│ └── test_user_profile.py                                   │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                INTEGRATION TEST DEPENDENCIES                 │
├─────────────────────────────────────────────────────────────┤
│ brokers.dhan.tests.integration/                           │
│ ├── test_live_options.py                                   │
│ ├── test_live_quotes.py                                    │
│ ├── test_live_validation.py                                │
│ ├── test_live_websocket.py                                 │
│ ├── test_symbol_mapping_live.py                           │
│ ├── test_ws_parity.py                                      │
│ └── test_live_quotes.py                                    │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                 TESTS/ INTEGRATION DEPENDENCIES             │
├─────────────────────────────────────────────────────────────┤
│ tests/integration/                                         │
│ ├── test_event_replay_determinism.py                        │
│ ├── test_event_log_replay.py                               │
│ ├── test_gateway_contract.py                               │
│ ├── test_kill_switch_atomic_flip.py                        │
│ └── test_processed_trade_repository_crash_recovery.py     │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                  ANALYTICS TEST DEPENDENCIES                 │
├─────────────────────────────────────────────────────────────┤
│ analytics/tests/                                           │
│ ├── test_backtest.py                                       │
│ ├── test_breadth.py                                        │
│ ├── test_core.py                                           │
│ ├── test_deep_dive.py                                      │
│ ├── test_features.py                                       │
│ ├── test_greeks.py                                         │
│ ├── test_halftrend.py                                     │
│ ├── test_indicators.py                                    │
│ ├── test_market_structure.py                              │
│ ├── test_orderflow.py                                      │
│ ├── test_options.py                                        │
│ ├── test_orderflow.py                                      │
│ ├── test_paper.py                                          │
│ ├── test_pipeline.py                                       │
│ ├── test_providers.py                                      │
│ ├── test_ranking_determinism.py                           │
│ ├── test_replay.py                                         │
│ ├── test_reports.py                                        │
│ ├── test_scanner.py                                        │
│ ├── test_sector.py                                         │
│ ├── test_stocks.py                                         │
│ ├── test_strategy.py                                       │
│ ├── test_volume_profile.py                                │
│ └── test_visualizations.py                                 │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                  E2E TEST DEPENDENCIES                       │
├─────────────────────────────────────────────────────────────┤
│ tests/e2e/                                                 │
│ └── test_order_lifecycle.py                                │
└─────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────┐
│                  CHAOS TEST DEPENDENCIES                     │
├─────────────────────────────────────────────────────────────┤
│ tests/chaos/                                                │
│ ├── test_failover.py                                       │
│ ├── test_failure_modes.py                                  │
│ └── test_recovery_certification.py                        │
└─────────────────────────────────────────────────────────────┘
