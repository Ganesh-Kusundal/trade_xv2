"""Infrastructure Provider Implementations — concrete DataProvider/ExecutionProvider.

These implementations wrap existing broker adapters, CSV files, and DataFrames
behind the DataProvider protocol defined in ``domain.ports.protocols``.

Submodules:
    broker/      — BrokerDataProvider (wraps MarketDataGateway)
    csv/         — CsvDataProvider (CSV files for notebooks)
    dataframe/   — DataFrameDataProvider (in-memory for tests)
"""
