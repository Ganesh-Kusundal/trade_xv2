"""Infrastructure Provider Implementations — concrete DataProvider/ExecutionProvider.

These implementations wrap existing broker adapters, CSV files, DataFrames,
and composite fallback chains behind the DataProvider protocol defined
in ``domain.providers``.

Submodules:
    broker/      — BrokerDataProvider (wraps MarketDataGateway)
    csv/         — CsvDataProvider (CSV files for notebooks)
    composite/   — CompositeDataProvider (fallback chain)
    dataframe/   — DataFrameDataProvider (in-memory for tests)
"""
