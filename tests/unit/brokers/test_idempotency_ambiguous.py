"""P0.4 regression: idempotency reservation must NOT be cleared on ambiguous
POST-success + response-parse-failure.

When the HTTP POST succeeds (order may have reached the broker) but
response parsing raises, clearing the reservation would allow a retry
with the same correlation_id to place a duplicate order.
"""

from __future__ import annotations

import unittest.mock as mock

import pytest

from brokers.common.idempotency import IdempotencyCache
from brokers.dhan.execution.order_placement import OrderPlacer
from domain import OrderResponse, OrderStatus
from domain.models.dtos import BrokerOrderPayload
from tests.support.brokers.dhan.fixtures import SAMPLE_ROWS, FakeHttpClient


def _make_request(cid: str = "ambiguous-cid") -> BrokerOrderPayload:
    return BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        correlation_id=cid,
    )


def _make_dhan_placer(fake_client, cache=None):
    from brokers.dhan.identity import coerce_identity_provider
    from brokers.dhan.resolver import SymbolResolver

    r = SymbolResolver()
    r.load_from_rows(list(SAMPLE_ROWS))
    identity = coerce_identity_provider(r)
    return OrderPlacer(
        client=fake_client,
        identity=identity,
        idempotency=cache or IdempotencyCache(),
        validator=mock.MagicMock(validate_order=lambda *a, **k: []),
        allow_live_orders=True,
    )


# ── Dhan ──────────────────────────────────────────────────────────────


class TestDhanAmbiguousPostSuccessParseFailure:
    """Dhan: POST succeeds, response parsing raises → reservation kept."""

    def test_reservation_not_cleared_on_parse_error(self):
        """After a successful POST that raises during response parsing,
        the idempotency reservation must remain so that a retry with
        the same correlation_id does not submit a duplicate order."""
        fake_client = FakeHttpClient()
        fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-AMB"}})
        cache = IdempotencyCache()
        placer = _make_dhan_placer(fake_client, cache)
        request = _make_request()

        with mock.patch.object(
            OrderPlacer,
            "_build_placed_order",
            side_effect=ValueError("malformed broker response"),
        ):
            with pytest.raises(ValueError, match="malformed broker response"):
                placer.place_order(request)

        # POST was sent → reservation must NOT have been cleared
        assert cache.reserve("ambiguous-cid") is False, (
            "Reservation should still be held after ambiguous POST-success + parse-failure"
        )

    def test_retry_after_ambiguous_failure_does_not_double_post(self):
        """A retry with the same correlation_id after an ambiguous failure
        must find the existing reservation and not send another POST."""
        fake_client = FakeHttpClient()
        fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-AMB2"}})
        cache = IdempotencyCache()
        placer = _make_dhan_placer(fake_client, cache)
        request = _make_request(cid="retry-cid")

        # First attempt: POST succeeds, parsing raises
        with mock.patch.object(
            OrderPlacer,
            "_build_placed_order",
            side_effect=ValueError("parse error"),
        ):
            with pytest.raises(ValueError):
                placer.place_order(request)

        assert fake_client.call_count == 1

        # Reservation is still held → retry blocks waiting for the first
        # caller to finish.  The key assertion is that the first failure
        # did NOT clear the reservation prematurely.
        assert cache.reserve("retry-cid") is False

    def test_pre_post_failure_still_clears_reservation(self):
        """A failure BEFORE the POST (e.g. validation) must still clear
        the reservation so the next caller can retry."""
        from brokers.dhan.identity import coerce_identity_provider
        from brokers.dhan.resolver import SymbolResolver

        fake_client = FakeHttpClient()
        r = SymbolResolver()
        r.load_from_rows(list(SAMPLE_ROWS))
        identity = coerce_identity_provider(r)
        cache = IdempotencyCache()
        placer = OrderPlacer(
            client=fake_client,
            identity=identity,
            idempotency=cache,
            validator=mock.MagicMock(
                validate_order=lambda *a, **k: ["invalid quantity"]
            ),
            allow_live_orders=True,
        )

        request = _make_request(cid="pre-post-cid")
        response = placer.place_order(request)

        assert response.success is False
        assert fake_client.call_count == 0
        # Pre-POST failure → reservation should be released
        assert cache.reserve("pre-post-cid") is True

    def test_post_transport_failure_clears_reservation(self):
        """A transport error (POST itself fails) must clear the reservation
        since the order definitely was not placed."""
        fake_client = FakeHttpClient()
        fake_client.set_side_effect(
            "POST", "/orders", ConnectionError("network down")
        )
        cache = IdempotencyCache()
        placer = _make_dhan_placer(fake_client, cache)
        request = _make_request(cid="transport-fail-cid")
        response = placer.place_order(request)

        assert response.success is False
        assert fake_client.call_count == 1
        # Transport failure → reservation should be released
        assert cache.reserve("transport-fail-cid") is True


# ── Upstox ────────────────────────────────────────────────────────────


class TestUpstoxAmbiguousPostSuccessParseFailure:
    """Upstox: POST succeeds, response parsing raises → reservation kept."""

    def test_reservation_not_cleared_on_parse_error(self):
        """After a successful POST that raises during response mapping,
        the idempotency reservation must remain."""
        from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
        from brokers.upstox.orders.order_command_adapter import (
            UpstoxOrderCommandAdapter,
        )

        cache = IdempotencyCache()
        order_client = mock.MagicMock()
        order_client.place_order_v3.return_value = {"data": {"order_id": "ORD-UPST"}}
        order_client.build_place_payload.return_value = {}

        resolver_mock = mock.MagicMock()
        resolver_mock.resolve.return_value = mock.MagicMock(
            instrument_key="NSE_EQ_RELIANCE"
        )

        adapter = UpstoxOrderCommandAdapter(
            order_client=order_client,
            instrument_resolver=resolver_mock,
            idempotency_cache=cache,
            use_v3=True,
        )

        request = _make_request(cid="upstox-amb-cid")

        with mock.patch.object(
            UpstoxDomainMapper,
            "to_order_response",
            side_effect=ValueError("unexpected response shape"),
        ):
            with pytest.raises(ValueError, match="unexpected response shape"):
                adapter.place_order(request)

        # POST was sent → reservation must NOT have been cleared
        assert cache.reserve("upstox-amb-cid") is False, (
            "Reservation should still be held after ambiguous POST-success + parse-failure"
        )

    def test_pre_post_failure_clears_reservation(self):
        """Upstox: failure before POST (instrument resolution) must clear
        the reservation."""
        from brokers.upstox.orders.order_command_adapter import (
            UpstoxOrderCommandAdapter,
        )

        cache = IdempotencyCache()
        order_client = mock.MagicMock()

        resolver_mock = mock.MagicMock()
        resolver_mock.resolve.side_effect = LookupError("instrument not found")

        adapter = UpstoxOrderCommandAdapter(
            order_client=order_client,
            instrument_resolver=resolver_mock,
            idempotency_cache=cache,
            use_v3=True,
        )

        request = _make_request(cid="upstox-pre-cid")

        with pytest.raises(LookupError):
            adapter.place_order(request)

        # Pre-POST failure → reservation should be released
        assert cache.reserve("upstox-pre-cid") is True
        order_client.place_order_v3.assert_not_called()
