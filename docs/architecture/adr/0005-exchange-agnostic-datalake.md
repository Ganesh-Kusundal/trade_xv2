# ADR-005: Exchange-agnostic datalake via ExchangeAdapter/TradingCalendar

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
The datalake bakes in NSE / IST specifics: `src/datalake/core/nse_calendar.py` (holidays
2020–2026), `constants.py:50` (09:15/15:30), `schema.py:25` (`"NSE"`, paise scaling),
and `exchange="NSE"` defaults in `analytics_provider.py:78`, `research/api.py:63`,
`option_format.py:78`. This blocks exchange-agnosticism and silently assumes Indian
markets.

## Decision
Introduce `ExchangeAdapter` + `TradingCalendar` ports (`target-layering.md` §3). Move all
exchange-specific conventions (calendar, session hours, symbol/exchange naming,
tick-size, lot-size, currency/paise) into exchange plugins under a new
`tradex.exchanges` entry-point group. Datalake imports conventions ONLY through the
active `ExchangeAdapter`. Until an exchange plugin is registered, datalake raises
`ExchangeNotConfigured` rather than defaulting to `"NSE"`. The existing `MarketSurface`
(`src/market_data/market_surface.py:32`) is the canonical carrier for these conventions.

## Consequences
- Positive: datalake becomes exchange-agnostic; no silent NSE assumption.
- Negative: NSE logic moves to a plugin; callers must register an exchange at startup.
- Cost: behavior change for any caller relying on the implicit NSE default — surfaced
  explicitly via `ExchangeNotConfigured`.

## Validation
- Grep: zero `exchange="NSE"`, zero `nse_calendar` references remain in `src/datalake`.
- A test asserts `DataLakeGateway.history(symbol)` without a registered exchange raises
  `ExchangeNotConfigured`.

## Status (contracts frozen 2026-07-12)
- **Status:** Accepted (contracts); implementation deferred to G3 / P5-2.
- The stable contracts P5-2 depends on now exist as pure domain ports:
  - `src/domain/ports/exchange_calendar.py` — `TradingCalendar` protocol
    (`exchange`, `timezone`, `is_trading_day`, `session_bounds`, `expected_bars`).
  - `src/domain/ports/exchange_adapter.py` — `ExchangeAdapter` protocol
    (`exchange`, `timezone`, `base_currency`, `price_scale`, `tick_size`,
    `lot_size`, `normalize_symbol`).
  - `src/domain/exceptions.py` — `ExchangeNotConfigured(DataError)`, the error
    callers raise instead of defaulting to `"NSE"`.
- Both ports are exported from `src/domain/ports/__init__.py` and are
  structurally satisfiable (verified by `tests/unit/domain/ports/test_exchange_ports.py`).
- These replace the hardcoded `EXCHANGE_CALENDARS` dict in
  `src/infrastructure/time_service.py:45` and the `"NSE"` literals in
  `src/datalake/**` at implementation time (P5-2). No behavior changed yet.
- Backlog cross-reference: **G3** (NSE/IST hardcodes) is the consumer; closing G3
  wires the NSE plugin to these ports and deletes the hardcoded constants.
