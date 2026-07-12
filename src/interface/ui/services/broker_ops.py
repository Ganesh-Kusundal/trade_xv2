"""UI → brokers.services seam — single broker ops path for tradex ui commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from brokers.platform_ops import (
    run_benchmark,
    run_certify,
    run_diagnose,
    run_doctor,
    run_health,
    run_mapping,
    run_verify,
)
from brokers.services import (
    cancel_order,
    get_capabilities,
    get_depth,
    get_funds,
    get_history,
    get_holdings,
    get_option_chain,
    get_orders,
    get_positions,
    get_quote,
    lookup_security,
    lookup_symbol,
    modify_order,
    place_order,
    run_connect,
    run_subscribe_probe,
)

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService


def broker_id_from(service: BrokerService | None, *, default: str = "paper") -> str:
    """Resolve active broker id from BrokerService or fall back to default."""
    if service is None:
        return default.lower()
    return (service.active_broker_name or default).lower()


def _bid(service: BrokerService | None, *, default: str = "paper", **kwargs: Any) -> tuple[str, dict[str, Any]]:
    return broker_id_from(service, default=default), kwargs


def fetch_connect(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> dict[str, Any]:
    broker, kw = _bid(service, default=default, **kwargs)
    return run_connect(broker, **kw)


def fetch_quote(
    service: BrokerService | None,
    symbol: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_quote(broker, symbol, exchange=exchange, **kw)


def fetch_history(
    service: BrokerService | None,
    symbol: str,
    *,
    timeframe: str = "1D",
    days: int = 5,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_history(broker, symbol, timeframe=timeframe, days=days, exchange=exchange, **kw)


def fetch_history_df(
    service: BrokerService | None,
    symbol: str,
    *,
    timeframe: str = "1D",
    days: int = 30,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    """Historical OHLCV as DataFrame via brokers.services."""
    series = fetch_history(
        service,
        symbol,
        timeframe=timeframe,
        days=days,
        exchange=exchange,
        default=default,
        **kwargs,
    )
    if hasattr(series, "to_dataframe"):
        return series.to_dataframe()
    if hasattr(series, "bars"):
        import pandas as pd

        bars = getattr(series, "bars", []) or []
        return pd.DataFrame(
            [
                {
                    "timestamp": getattr(b, "timestamp", None),
                    "open": float(getattr(b, "open", 0)),
                    "high": float(getattr(b, "high", 0)),
                    "low": float(getattr(b, "low", 0)),
                    "close": float(getattr(b, "close", 0)),
                    "volume": int(getattr(b, "volume", 0)),
                }
                for b in bars
            ]
        )
    return series


def fetch_depth(
    service: BrokerService | None,
    symbol: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_depth(broker, symbol, exchange=exchange, **kw)


def fetch_option_chain(
    service: BrokerService | None,
    underlying: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_option_chain(broker, underlying, exchange=exchange, **kw)


def fetch_funds(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_funds(broker, **kw)


def fetch_positions(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_positions(broker, **kw)


def fetch_holdings(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_holdings(broker, **kw)


def fetch_orders(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_orders(broker, **kw)


def fetch_capabilities(
    service: BrokerService | None,
    symbol: str = "RELIANCE",
    *,
    default: str = "paper",
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return get_capabilities(broker, symbol, **kw)


def resolve_symbol(
    service: BrokerService | None,
    symbol: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> str:
    broker, kw = _bid(service, default=default, **kwargs)
    return lookup_symbol(broker, symbol, exchange=exchange, **kw)


def resolve_security(
    service: BrokerService | None,
    symbol: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> dict[str, Any]:
    broker, kw = _bid(service, default=default, **kwargs)
    return lookup_security(broker, symbol, exchange=exchange, **kw)


def probe_subscribe(
    service: BrokerService | None,
    symbol: str,
    *,
    exchange: str = "NSE",
    default: str = "paper",
    **kwargs: Any,
) -> bool:
    broker, kw = _bid(service, default=default, **kwargs)
    return run_subscribe_probe(broker, symbol, exchange=exchange, **kw)


def verify_broker(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return run_verify(broker, **kw)


def doctor_broker(service: BrokerService | None = None, *, default: str = "paper") -> Any:
    broker = broker_id_from(service, default=default)
    return run_doctor(broker)


def diagnose_broker(service: BrokerService | None = None, *, default: str = "paper", **kwargs: Any) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return run_diagnose(broker, **kw)


def health_broker(service: BrokerService | None = None, *, default: str = "paper") -> Any:
    broker = broker_id_from(service, default=default)
    return run_health(broker)


def benchmark_broker(service: BrokerService | None = None, *, default: str = "paper") -> Any:
    broker = broker_id_from(service, default=default)
    return run_benchmark(broker)


def certify_broker(
    service: BrokerService | None = None,
    *,
    default: str = "paper",
    live: bool = False,
    **kwargs: Any,
) -> Any:
    broker, kw = _bid(service, default=default, **kwargs)
    return run_certify(broker, live=live, **kw)


def mapping_broker(service: BrokerService | None = None, *, default: str = "paper") -> Any:
    broker = broker_id_from(service, default=default)
    return run_mapping(broker)


__all__ = [
    "benchmark_broker",
    "broker_id_from",
    "cancel_order",
    "certify_broker",
    "diagnose_broker",
    "doctor_broker",
    "fetch_capabilities",
    "fetch_connect",
    "fetch_depth",
    "fetch_funds",
    "fetch_history",
    "fetch_history_df",
    "fetch_holdings",
    "fetch_option_chain",
    "fetch_orders",
    "fetch_positions",
    "fetch_quote",
    "health_broker",
    "mapping_broker",
    "modify_order",
    "place_order",
    "probe_subscribe",
    "resolve_security",
    "resolve_symbol",
    "verify_broker",
]
