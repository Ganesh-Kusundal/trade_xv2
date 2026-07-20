"""Runtime bridge for interface layer — no direct brokers.* imports in UI/API."""

from __future__ import annotations

from typing import Any, Callable


def check_live_actionable(broker_name: str) -> None:
    from brokers.services._session import check_live_actionable as _check

    _check(broker_name)


def set_live_actionable_gate(value: bool) -> None:
    from brokers.services._session import set_live_actionable_gate as _set

    _set(value)


def run_doctor(*args: Any, **kwargs: Any) -> Any:
    from brokers.platform_ops import run_doctor as _run

    return _run(*args, **kwargs)


def run_verify(*args: Any, **kwargs: Any) -> Any:
    from brokers.platform_ops import run_verify as _run

    return _run(*args, **kwargs)


def run_benchmark(*args: Any, **kwargs: Any) -> Any:
    from brokers.platform_ops import run_benchmark as _run

    return _run(*args, **kwargs)


def broker_session_type() -> type:
    from brokers.session import BrokerSession

    return BrokerSession


def cancel_order(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import cancel_order as _fn

    return _fn(*args, **kwargs)


def get_depth(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_depth as _fn

    return _fn(*args, **kwargs)


def get_funds(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_funds as _fn

    return _fn(*args, **kwargs)


def get_history(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_history as _fn

    return _fn(*args, **kwargs)


def get_holdings(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_holdings as _fn

    return _fn(*args, **kwargs)


def get_option_chain(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_option_chain as _fn

    return _fn(*args, **kwargs)


def get_positions(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_positions as _fn

    return _fn(*args, **kwargs)


def get_quote(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import get_quote as _fn

    return _fn(*args, **kwargs)


def lookup_security(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import lookup_security as _fn

    return _fn(*args, **kwargs)


def run_certify(*args: Any, **kwargs: Any) -> Any:
    from brokers.services import run_certify as _fn

    return _fn(*args, **kwargs)
