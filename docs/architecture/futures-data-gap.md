# Futures Data Infrastructure Gap

**Date:** 2026-07-19
**Status:** Gap identified — no ingestion path exists
**Priority:** High (blocks futures-dependent strategies)

---

## Executive Summary

The domain layer has rich futures support (`FutureChain`, `FutureContract`, derivatives math, instrument resolver), but **zero infrastructure exists to ingest or sync futures data into the datalake**. The gateway's `future_chain()` method reads from `futures/chains/` — a path that nothing writes to.

---

## What Exists

### Domain Layer (Complete)

| Component | Location | Status |
|-----------|----------|--------|
| `FutureChain` value object | `domain/entities/options.py:161` | ✅ Complete |
| `FutureContract` value object | `domain/entities/options.py:127` | ✅ Complete |
| `FutureChain` aggregate | `domain/futures/future_chain.py` | ✅ Complete |
| Future instrument ID | `domain/instruments/instrument_id.py:153` | ✅ Complete |
| Derivatives math | `domain/instruments/derivatives_math.py` | ✅ Complete |
| Instrument resolver (futures pattern) | `domain/instrument_resolver.py:41` | ✅ Complete |
| Broker capabilities (FUTURES enum) | `domain/capabilities/enums.py:21` | ✅ Complete |
| Analytics adapter | `datalake/adapters/analytics_provider.py:95` | ✅ Complete |

### Datalake Layer (Partial)

| Component | Location | Status |
|-----------|----------|--------|
| Gateway `future_chain()` reader | `datalake/gateway.py:285` | ⚠️ Reads but nothing writes |
| Partition scheme | `datalake/core/paths.py` | ❌ No futures partitions |
| Ingestion pipeline | `datalake/ingestion/` | ❌ No futures sync |

---

## What's Missing

### 1. Partition Scheme (`datalake/core/paths.py`)

Current partitions support only equities and options:

```
{root}/equities/candles/timeframe={timeframe}/symbol={symbol}/data.parquet
{root}/options/chains/expiry={expiry}/underlying={underlying}/data.parquet
```

**Missing:** Futures partition for chain data and OHLCV candles.

Proposed layout:
```
{root}/futures/chains/underlying={underlying}/data.parquet
{root}/futures/candles/symbol={symbol}/timeframe={timeframe}/data.parquet
```

### 2. Ingestion/Sync Path (`datalake/ingestion/`)

No `sync_futures.py` or equivalent exists. Need:
- Futures chain sync (fetch from broker, write to `futures/chains/`)
- Futures OHLCV sync (fetch historical candles per contract, write to `futures/candles/`)
- Contract rollover handling (monthly expiry detection, chain refresh)

### 3. Path Constants

`paths.py` has no futures constants. Needs:
- `FUTURES_CHAINS` segment
- `FUTURES_CANDLES` segment  
- `PARTITION_CONTRACT` for contract identifier
- `futures_chain_path()` helper
- `futures_candle_path()` helper

### 4. Gateway Wiring

`gateway.py:285` reads `futures/chains/` but:
- No writer populates this path
- No refresh mechanism (stale data risk)
- No fallback to broker API when lake is empty

---

## Estimated Effort

| Work Item | Size | Notes |
|-----------|------|-------|
| Add futures partition constants to `paths.py` | S | Add segments + helper functions |
| Create `sync_futures_chains.py` | M | Fetch from Dhan/Upstox, write parquet |
| Create `sync_futures_candles.py` | M | Historical OHLCV per contract |
| Wire gateway refresh | S | Call sync when lake is empty/stale |
| Add contract rollover logic | M | Detect expiry, refresh chain |
| Tests | M | Unit + integration for sync paths |

**Total estimate:** ~2-3 days for MVP (chain sync + candle sync)

---

## Risk

- **Stale chain data:** Without sync, `future_chain()` returns empty lists or outdated contracts.
- **Rollover gaps:** No mechanism to detect when a contract expires and switch to the next.
- **Broken strategies:** Any strategy depending on futures data silently fails.

---

## Recommendation

Prioritize futures chain sync as the first deliverable — it unblocks the most downstream consumers. Candle sync can follow.
