# ADR-006: Exchange Resolution Layer Model

## Context

Exchange segment strings were duplicated across six modules with inconsistent
wire spellings (`MCX_COMM` vs `MCXCOMM`) and a silent MCX→NSE fallback in the
Dhan gateway.

## Decision

1. **Canonical layer:** `ExchangeSegment` enum + `parse_segment()` in
   `brokers/common/core/exchange_segments.py`.
2. **Broker wire adapters:** `brokers/dhan/segments.py` (`to_dhan_wire`,
   `to_sdk_int`) and `brokers/upstox/instruments/segment_mapper.py`.
3. **Failure mode:** explicit `ValueError` — never silent fallback.

## Consequences

- All production call sites use `parse_segment()` for inbound resolution.
- Dhan HTTP and SDK integer mappings live in one adapter module.
- Architecture tests block new inline alias dicts outside approved modules.
