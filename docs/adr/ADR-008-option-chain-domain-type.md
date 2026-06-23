# ADR-008: Option Chain Domain Type

## Context

`MarketDataGateway.option_chain()` returned untyped `dict` values. Callers
duplicated parsing logic and could not rely on static typing or schema tests.

## Decision

1. Introduce frozen dataclasses in `brokers/common/core/models.py`:
   `OptionLeg`, `OptionStrike`, `OptionChain`, `FutureContract`, `FutureChain`.
2. Gateway contract methods return these types; `to_dict()` / `from_dict()` preserve
   backward compatibility during migration.
3. `brokers/common/options/chain_normalizer.py` builds `OptionChain` from
   broker payloads.

## Consequences

- CLI and analytics can use typed models or `.to_dict()` at presentation boundaries.
- Contract tests can validate schema parity with the legacy dict shape.
- Datalake API schemas may map from domain types without re-parsing raw dicts.
