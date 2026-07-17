"""Historical data chunking pipeline — DEPRECATED.

This divergent single-broker pipeline was replaced by the federated
``HistoricalDataCoordinator`` (``application.data.historical_coordinator``),
which is now the single source of truth for historical data and is shared by
both the live API and ``BrokerSession`` (zero-parity).

All historical fetches now flow through:
    BrokerSession.history() / history_batch()
        -> HistoricalDataCoordinator.fetch_sync()
        -> CommonBrokerGateway.get_historical_bars()

The coordinator provides chunk planning, conflict resolution, explicit gap
detection and degraded-mode reporting that this module lacked. Do not add new
code here.
"""