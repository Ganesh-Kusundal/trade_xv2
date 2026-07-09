# Data Lake Scanner (research SQL path)

**Ownership (ENG-020):** Offline / research screening over the datalake.

- Compiles rules to SQL against Parquet/DuckDB
- **Does not** emit live trading candidates or talk to the OMS

For live automated trading candidates, use **`analytics.scanner`** only.
