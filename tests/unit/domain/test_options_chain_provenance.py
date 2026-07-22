"""WS-D — option/future chain ingress provenance (fetched_at)."""

from __future__ import annotations

from datetime import datetime, timezone

from domain.entities.options import FutureChain, OptionChain
from domain.ports.time_service import use_clock
from domain.ports.time_service_impls import VirtualClock


def test_option_chain_from_dict_stamps_fetched_at_when_missing() -> None:
    fixed = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    payload = {"underlying": "NIFTY", "exchange": "NFO", "expiry": "2026-12-31", "strikes": []}

    with use_clock(VirtualClock(initial=fixed)):
        chain = OptionChain.from_dict(payload)

    assert chain.fetched_at == fixed


def test_option_chain_from_dict_preserves_fetched_at_in_payload() -> None:
    stamped = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    later = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    payload = {
        "underlying": "NIFTY",
        "exchange": "NFO",
        "expiry": "2026-12-31",
        "strikes": [],
        "fetched_at": stamped.isoformat(),
    }

    with use_clock(VirtualClock(initial=later)):
        chain = OptionChain.from_dict(payload)

    assert chain.fetched_at == stamped


def test_future_chain_from_dict_stamps_fetched_at_when_missing() -> None:
    fixed = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    payload = {"underlying": "NIFTY", "exchange": "NFO", "contracts": []}

    with use_clock(VirtualClock(initial=fixed)):
        chain = FutureChain.from_dict(payload)

    assert chain.fetched_at == fixed


def test_future_chain_from_dict_preserves_fetched_at_in_payload() -> None:
    stamped = datetime(2026, 6, 1, 9, 30, tzinfo=timezone.utc)
    later = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    payload = {
        "underlying": "NIFTY",
        "exchange": "NFO",
        "contracts": [],
        "fetched_at": stamped.isoformat(),
    }

    with use_clock(VirtualClock(initial=later)):
        chain = FutureChain.from_dict(payload)

    assert chain.fetched_at == stamped


def test_chain_to_dict_roundtrip_preserves_fetched_at() -> None:
    fixed = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    payload = {"underlying": "NIFTY", "exchange": "NFO", "expiry": "2026-12-31", "strikes": []}

    with use_clock(VirtualClock(initial=fixed)):
        option = OptionChain.from_dict(payload)
        future = FutureChain.from_dict({"underlying": "NIFTY", "exchange": "NFO", "contracts": []})

    restored_option = OptionChain.from_dict(option.to_dict())
    restored_future = FutureChain.from_dict(future.to_dict())

    assert restored_option.fetched_at == fixed
    assert restored_future.fetched_at == fixed
