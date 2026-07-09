# Quote vs QuoteSnapshot (ENG-033)

| Type | Module | Role |
|------|--------|------|
| **Quote** | `domain.entities.market.Quote` | Broker REST / book snapshot entity (symbol-centric fields) |
| **QuoteSnapshot** | `domain.entities.market.QuoteSnapshot` | Live instrument state on `Instrument` (InstrumentRef + provenance) |

## Conversion

```python
snapshot = quote.to_snapshot(provenance=...)
quote2 = snapshot.to_quote()
```

Adapters should map broker payloads → **Quote** at the gateway boundary, then
`to_snapshot()` when injecting into `Instrument` / DataProvider consumers.
Do not invent a third quote type.
