# scripts/debug/

Ad-hoc diagnostic / debug scripts. **Not** collected by pytest (filenames
deliberately do not start with `test_`).

Run any of these from the project root:

```bash
python scripts/debug/broker_load_check.py
python scripts/debug/catalog_inspect.py
python scripts/debug/minimal_resolver_check.py
python scripts/debug/futures_contracts_bug.py
python scripts/debug/futures_contracts_p1.py
```

| Script | Purpose |
|---|---|
| `broker_load_check.py` | Why does `DhanBroker.from_env()` fall back to `MockBroker`? Step-by-step import + `from_env` + live API call traceback. |
| `catalog_inspect.py` | Loads the DhanBroker and inspects the instrument resolver state (loaded, size, RELIANCE matches) **before** downloading the catalog. |
| `minimal_resolver_check.py` | Minimal probe of the resolver state and live funds / positions / holdings. Writes its output to `debug_output.txt`. |
| `futures_contracts_bug.py` | Full reproduction of the NIFTY-futures "No contracts found" bug — empty vs. loaded catalog, nearest contract, and adapter path. |
| `futures_contracts_p1.py` | Phase 1 of the futures-contracts reproduction (empty catalog only). |
| `catalog_inspect.ipynb` | Empty scratch notebook (kept as a starting point for exploratory data work). |

All scripts assume a valid `.env.local` at the project root with Dhan credentials.
