# ADR-004: Parallel Fetching via BatchFetchMixin

## Context
The `ltp_batch`, `quote_batch`, and `history_batch` methods were implemented with nearly identical `ThreadPoolExecutor` code in every gateway (Dhan, Upstox, Paper).

## Decision
- A `BatchFetchMixin` in `brokers/common/batch_mixin.py` provides default implementations using `ThreadPoolExecutor`
- Gateways inherit the mixin and only need to implement the single-item methods (`ltp`, `quote`, `history`)
- Brokers with native batch APIs (e.g., Dhan's `get_batch_ltp`) override the mixin methods

## Consequences
- Parallel fetch code exists in one place
- New gateways get batch operations for free
- Native batch APIs can still be used for better performance
