# Exchange Plugin Gap: BSE / NFO

> Part of Phase 0 Architecture Discovery. This document identifies the missing
> BSE and NFO exchange plugin implementations and catalogs the NSE-specific
> assumptions still present in the codebase.

## 1. What Exists

Only one exchange plugin is implemented:

| Plugin | Entry-point | Adapter | Calendar |
|--------|-------------|---------|----------|
| **NSE** | `plugins.exchanges.nse` | `NseExchangeAdapter` | `NseTradingCalendar` |

Registered in `pyproject.toml` under `[project.entry-points."tradex.exchanges"]`:
```
nse = "plugins.exchanges.nse"
```

The NSE plugin satisfies two domain ports:
- `domain.ports.ExchangeAdapter` — exchange conventions (timezone, price_scale, tick_size, lot_size, normalize_symbol)
- `domain.ports.TradingCalendar` — trading day/holiday calendar, session bounds, expected bars

## 2. What's Missing

### BSE (Bombay Stock Exchange) — Equity + BFO

The domain layer already models BSE:
- `ExchangeSegment.BSE` (wire: `"BSE_EQ"`) in `domain/market_enums.py`
- `ExchangeSegment.BSE_FNO` (wire: `"BSE_FNO"`) in `domain/market_enums.py`
- `ExchangeSegment.BSE_CURRENCY` (wire: `"BSE_CURRENCY"`) in `domain/market_enums.py`
- `BSEExchangeAdapter` stub in `domain/market/exchange_adapters.py` (basic `is_trading_hours`/`is_trading_day`)
- Segment aliases `"BSE"`, `"BSE_EQ"`, `"BFO"`, `"BSE_FNO"`, `"BCD"`, `"BSE_CURRENCY"` in `domain/exchange_segments.py`

**What's missing:**
- `src/plugins/exchanges/bse/` directory with:
  - `adapter.py` — full `ExchangeAdapter` implementation (price_scale, tick_size, lot_size, calendar binding)
  - `calendar.py` — BSE `TradingCalendar` with BSE-specific holidays (BSE publishes its own holiday list)
  - `__init__.py` — module-level `ADAPTER` and `CALENDAR` instances
- Entry-point registration in `pyproject.toml`

### NFO (NSE F&O / Derivatives)

NFO is an exchange *segment* of NSE, not a separate exchange. The domain already models it:
- `ExchangeSegment.NSE_FNO` (wire: `"NSE_FNO"`) in `domain/market_enums.py`
- `Exchange.NFO` in `domain/market_enums.py`
- Segment aliases `"NFO"`, `"NSE_FNO"` in `domain/exchange_segments.py`

**What's missing:**
- NFO uses the same trading calendar as NSE equity, but with different session hours (9:00 AM – 3:30 PM for futures, 9:15 AM – 3:30 PM for options — depending on instrument).
- A dedicated NFO plugin is **not strictly required** if the NSE adapter handles derivative segments. However, if NFO needs distinct session hours or lot-size conventions, a separate adapter or parameterized NSE adapter variant is needed.
- The current `NseExchangeAdapter.lot_size = 1` is equity-specific; F&O lot sizes vary per underlying (e.g., NIFTY lot = 50, BANKNIFTY lot = 15).

### MCX (Multi Commodity Exchange)

Also missing, but lower priority:
- `ExchangeSegment.MCX` exists in the domain
- `MCXExchangeAdapter` stub exists in `domain/market/exchange_adapters.py`
- No plugin directory

## 3. NSE-Specific Hardcoded Assumptions

Despite the plugin architecture (ADR-005), many locations still default to or hardcode NSE:

### 3.1 Datalake Gateway — default `"NSE"` on every method signature

| File | Lines | Issue |
|------|-------|-------|
| `datalake/gateway.py` | 118, 146, 194, 215, 222, 229, 288, 316, 370, 373, 379, 425 | `exchange: str = "NSE"` as default parameter |
| `datalake/gateway.py` | 118 | Fallback `"NSE"` when exchange column missing from DataFrame |

### 3.2 Datalake Core — direct `nse_calendar` imports

| File | Lines | Issue |
|------|-------|-------|
| `datalake/core/__init__.py` | 42–54 | Re-exports `nse_calendar` functions at package level |
| `datalake/ingestion/loader.py` | 142, 305, 486 | Direct `from datalake.core.nse_calendar import ...` |
| `datalake/quality/monitor.py` | 87, 108 | Direct `from datalake.core.nse_calendar import ...` |

These files bypass the `exchange_registry` and use NSE-specific calendar functions directly.

### 3.3 Infrastructure — default `"NSE"` in provider signatures

| File | Lines | Issue |
|------|-------|-------|
| `infrastructure/providers/dataframe/dataframe_data_provider.py` | 150 | `exchange or "NSE"` fallback |
| `infrastructure/providers/broker/broker_data_provider.py` | 227, 248 | `"NSE"` fallback |
| `infrastructure/providers/csv/csv_data_provider.py` | 206 | `exchange or "NSE"` fallback |
| `infrastructure/historical_data.py` | 236 | `"NSE"` fallback |
| `infrastructure/time_service.py` | 20 | `exchange_now("NSE")` hardcoded |
| `infrastructure/adapters/market_data_gateway_adapter.py` | 79, 254, 268 | `"NSE"` fallback |
| `infrastructure/batch_mixin.py` | 22, 36, 46 | `exchange: str = "NSE"` default |
| `infrastructure/market_data_adapter.py` | 60, 82 | `exchange: str = "NSE"` default |

### 3.4 Domain Constants — NSE session hours as named constants

| File | Lines | Issue |
|------|-------|-------|
| `domain/constants/market.py` | 46 | `DEFAULT_EXCHANGE_SEGMENT_FALLBACK = "NSE_EQ"` |
| `domain/constants/market.py` | 63–72 | `NSE_OPEN_HOUR_IST`, `NSE_CLOSE_HOUR_IST`, etc. |
| `domain/market/hours.py` | 18–19 | `NSE_EQUITY_OPEN`, `NSE_EQUITY_CLOSE` (used by both NSE and BSE adapters) |

### 3.5 Datalake Symbols — default exchange strings

| File | Lines | Issue |
|------|-------|-------|
| `datalake/core/symbols.py` | 94, 107, 135 | `exchange: str = "NSE"` / `"NFO"` defaults |
| `datalake/core/schema.py` | 26 | Column comment: `"NSE", "BSE", "NFO"` |

## 4. What a BSE Plugin Requires

Based on the NSE reference implementation and the `ExchangeAdapter` + `TradingCalendar` ports:

### 4.1 `BseExchangeAdapter` (implements `ExchangeAdapter`)

| Property | BSE Value | Notes |
|----------|-----------|-------|
| `exchange` | `"BSE"` | |
| `timezone` | `"Asia/Kolkata"` | Same as NSE |
| `base_currency` | `"INR"` | Same as NSE |
| `price_scale` | `100` | BSE also uses paise on wire |
| `tick_size` | `0.05` | Same as NSE for most equities |
| `lot_size` | `1` | Equity default; F&O varies |
| `normalize_symbol` | uppercase + strip | Same as NSE |
| `calendar` | `BseTradingCalendar` | BSE has its own holiday list |

### 4.2 `BseTradingCalendar` (implements `TradingCalendar`)

- BSE publishes its own holiday list (mostly overlapping with NSE, but not identical).
- Session hours: 9:15 AM – 3:30 PM IST (same as NSE equity currently).
- Must implement: `is_trading_day()`, `session_bounds()`, `expected_bars()`.

### 4.3 Entry-point registration

```toml
[project.entry-points."tradex.exchanges"]
nse = "plugins.exchanges.nse"
bse = "plugins.exchanges.bse"
```

## 5. Effort Estimate

| Component | Effort | Risk |
|-----------|--------|------|
| BSE adapter (`adapter.py`) | Low | Port is well-defined; NSE is a template |
| BSE calendar (`calendar.py`) | Medium | Holiday list sourcing; BSE may differ from NSE |
| BSE `__init__.py` + entry-point | Trivial | Copy from NSE, change class names |
| NFO handling | Low–Medium | Decide: separate plugin or parameterized NSE adapter |
| Migrate datalake `nse_calendar` callers to `exchange_registry` | Medium | ~8 call sites in 4 files |
| Remove `"NSE"` default fallbacks | Low | Replace with `get_active_exchange_code()` or raise |
| Tests | Medium | Calendar tests for BSE holidays |

**Total estimated effort:** 1–2 days for BSE equity plugin; additional 0.5 day for NFO parameterization.

## 6. Recommendations

1. **Create BSE plugin first** — lowest risk, follows NSE pattern exactly.
2. **BSE holiday list** — source from BSE's official circulars; cross-reference with NSE where they overlap.
3. **NFO as NSE derivative segment** — do NOT create a separate NFO plugin. Instead, add a `segment` parameter or variant to the NSE adapter (NFO shares NSE's calendar). Lot sizes should come from instrument metadata, not the adapter.
4. **Migrate `nse_calendar` callers** — the ~8 direct imports in `datalake/core/__init__.py`, `ingestion/loader.py`, and `quality/monitor.py` should use `exchange_registry.get_active_adapter().calendar` instead.
5. **Remove `"NSE"` default fallbacks** — default exchange parameters in gateway/provider signatures should either use `get_active_exchange_code()` or require an explicit exchange argument.
6. **MCX plugin** — defer to a later phase; it has different session hours (9:00 AM – 11:30 PM / 11:55 PM) and commodity-specific conventions.
