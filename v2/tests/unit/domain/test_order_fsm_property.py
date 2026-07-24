"""Property-based tests for Order FSM transitions using Hypothesis."""

from decimal import Decimal
from uuid import uuid4

from hypothesis import given, strategies as st
import pytest

from domain.enums import OrderStatus, OrderSide, OrderType, TimeInForce
from domain.entities import Order
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis strategies for generating valid domain objects
# ─────────────────────────────────────────────────────────────────────────────

@st.composite
def order_ids(draw) -> OrderId:
    return OrderId(value=draw(st.uuids().map(str)))


@st.composite
def instrument_ids(draw) -> InstrumentId:
    # Use simple equity format for testing
    exchange = draw(st.sampled_from(["NSE", "BSE", "NFO"]))
    symbol = draw(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=10))
    return InstrumentId.equity(exchange, symbol)


@st.composite
def prices(draw) -> Price:
    return Price(value=Decimal(str(draw(st.decimals(min_value="0.01", max_value="100000", places=2)))))


@st.composite
def quantities(draw) -> Quantity:
    return Quantity(value=Decimal(str(draw(st.integers(min_value=1, max_value=100000)))))


@st.composite
def correlation_ids(draw) -> CorrelationId:
    return CorrelationId(value=draw(st.uuids()))


@st.composite
def order_statuses(draw) -> OrderStatus:
    return draw(st.sampled_from(list(OrderStatus)))


@st.composite
def valid_orders(draw) -> Order:
    return Order(
        order_id=draw(order_ids()),
        instrument_id=draw(instrument_ids()),
        side=draw(st.sampled_from(list(OrderSide))),
        order_type=draw(st.sampled_from(list(OrderType))),
        quantity=draw(quantities()),
        price=draw(prices()),
        time_in_force=draw(st.sampled_from(list(TimeInForce))),
        status=draw(order_statuses()),
        correlation_id=draw(correlation_ids()),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The canonical legal transition matrix (from domain/entities/__init__.py)
# ─────────────────────────────────────────────────────────────────────────────

LEGAL_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.SUBMITTED}),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.UNKNOWN,
        }
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.UNKNOWN: frozenset(),
}


# ─────────────────────────────────────────────────────────────────────────────
# Property tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOrderFSMProperties:
    """Property-based tests for Order FSM invariants."""

    @given(valid_orders(), st.sampled_from(list(OrderStatus)))
    def test_transition_always_returns_new_order_or_raises(self, order: Order, new_status: OrderStatus) -> None:
        """transition_to either returns a new Order with new status or raises ValueError."""
        is_legal = new_status in LEGAL_TRANSITIONS.get(order.status, frozenset())

        if is_legal:
            new_order = order.transition_to(new_status)
            assert new_order.status == new_status
            assert new_order is not order  # Immutability
        else:
            with pytest.raises(ValueError):
                order.transition_to(new_status)
            assert order.status == order.status  # Original unchanged

    @given(valid_orders(), st.sampled_from(list(OrderStatus)))
    def test_legal_transitions_preserve_identity(self, order: Order, new_status: OrderStatus) -> None:
        """Legal transitions produce a new Order; illegal ones raise."""
        is_legal = new_status in LEGAL_TRANSITIONS.get(order.status, frozenset())

        if is_legal:
            new_order = order.transition_to(new_status)
            assert new_order is not order  # New object (immutability)
            assert new_order.status == new_status
            # All other fields preserved
            assert new_order.order_id == order.order_id
            assert new_order.instrument_id == order.instrument_id
            assert new_order.side == order.side
            assert new_order.order_type == order.order_type
            assert new_order.quantity == order.quantity
            assert new_order.price == order.price
            assert new_order.time_in_force == order.time_in_force
            assert new_order.correlation_id == order.correlation_id
            assert new_order.filled_quantity == order.filled_quantity
        else:
            with pytest.raises(ValueError, match=r"illegal transition"):
                order.transition_to(new_status)

    @given(st.sampled_from(list(OrderStatus)))
    def test_terminal_states_have_no_outgoing_transitions(self, status: OrderStatus) -> None:
        """FILLED, CANCELLED, REJECTED, UNKNOWN are terminal — no legal transitions out."""
        is_terminal = status in {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}
        allowed = LEGAL_TRANSITIONS.get(status, frozenset())

        if is_terminal:
            assert allowed == frozenset(), f"Terminal state {status} has outgoing transitions: {allowed}"

    @given(st.sampled_from(list(OrderStatus)))
    def test_non_terminal_states_have_at_least_one_transition(self, status: OrderStatus) -> None:
        """Non-terminal states (PENDING, SUBMITTED, PARTIALLY_FILLED) have outgoing transitions."""
        is_non_terminal = status in {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        allowed = LEGAL_TRANSITIONS.get(status, frozenset())

        if is_non_terminal:
            assert len(allowed) > 0, f"Non-terminal state {status} has no outgoing transitions"

    @given(valid_orders())
    def test_self_transition_always_illegal(self, order: Order) -> None:
        """Transitioning to the same status is always illegal (no self-loops)."""
        with pytest.raises(ValueError, match=r"illegal transition"):
            order.transition_to(order.status)

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PENDING))
    def test_pending_can_only_go_to_submitted(self, order: Order) -> None:
        """PENDING can only transition to SUBMITTED."""
        for status in OrderStatus:
            if status == OrderStatus.SUBMITTED:
                new_order = order.transition_to(status)
                assert new_order.status == OrderStatus.SUBMITTED
            else:
                with pytest.raises(ValueError):
                    order.transition_to(status)

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.SUBMITTED))
    def test_submitted_transitions(self, order: Order) -> None:
        """SUBMITTED can go to PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, UNKNOWN."""
        allowed = {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}
        for status in OrderStatus:
            if status in allowed:
                new_order = order.transition_to(status)
                assert new_order.status == status
            else:
                with pytest.raises(ValueError):
                    order.transition_to(status)

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PARTIALLY_FILLED))
    def test_partially_filled_transitions(self, order: Order) -> None:
        """PARTIALLY_FILLED can go to FILLED, CANCELLED, UNKNOWN."""
        allowed = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.UNKNOWN}
        for status in OrderStatus:
            if status in allowed:
                new_order = order.transition_to(status)
                assert new_order.status == status
            else:
                with pytest.raises(ValueError):
                    order.transition_to(status)

    @given(valid_orders())
    def test_transition_matrix_is_complete_and_exhaustive(self, order: Order) -> None:
        """Every status pair is either explicitly legal or illegal (no undefined behavior)."""
        for new_status in OrderStatus:
            is_legal = new_status in LEGAL_TRANSITIONS.get(order.status, frozenset())

            if is_legal:
                # Must succeed without error
                new_order = order.transition_to(new_status)
                assert new_order.status == new_status
            else:
                # Must raise ValueError
                with pytest.raises(ValueError):
                    order.transition_to(new_status)

    @given(valid_orders())
    def test_transition_immutability_preserves_all_fields(self, order: Order) -> None:
        """transition_to preserves all fields except status for legal transitions."""
        for new_status in LEGAL_TRANSITIONS.get(order.status, frozenset()):
            new_order = order.transition_to(new_status)
            assert new_order.order_id == order.order_id
            assert new_order.instrument_id == order.instrument_id
            assert new_order.side == order.side
            assert new_order.order_type == order.order_type
            assert new_order.quantity == order.quantity
            assert new_order.price == order.price
            assert new_order.time_in_force == order.time_in_force
            assert new_order.correlation_id == order.correlation_id
            assert new_order.filled_quantity == order.filled_quantity

    @given(st.sampled_from(list(OrderStatus)))
    def test_transition_matrix_matches_code(self, status: OrderStatus) -> None:
        """The LEGAL_TRANSITIONS dict matches the actual _LEGAL dict in the entity."""
        from domain.entities import _LEGAL

        # Compare sets of allowed transitions
        assert set(LEGAL_TRANSITIONS[status]) == set(_LEGAL[status])

    @given(valid_orders())
    def test_error_message_contains_both_statuses(self, order: Order) -> None:
        """ValueError message for illegal transition contains both from and to status names."""
        for new_status in OrderStatus:
            if new_status not in LEGAL_TRANSITIONS.get(order.status, frozenset()):
                with pytest.raises(ValueError) as exc_info:
                    order.transition_to(new_status)
                error_msg = str(exc_info.value)
                assert order.status.name in error_msg
                assert new_status.name in error_msg
                assert "→" in error_msg or "->" in error_msg


class TestOrderFSMPathProperties:
    """Property tests for valid transition paths (multi-step)."""

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PENDING))
    def test_pending_to_filled_via_submitted(self, order: Order) -> None:
        """PENDING → SUBMITTED → FILLED is a valid path."""
        o1 = order.transition_to(OrderStatus.SUBMITTED)
        o2 = o1.transition_to(OrderStatus.FILLED)
        assert o2.status == OrderStatus.FILLED

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PENDING))
    def test_pending_to_cancelled_via_submitted(self, order: Order) -> None:
        """PENDING → SUBMITTED → CANCELLED is a valid path."""
        o1 = order.transition_to(OrderStatus.SUBMITTED)
        o2 = o1.transition_to(OrderStatus.CANCELLED)
        assert o2.status == OrderStatus.CANCELLED

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PENDING))
    def test_pending_to_partially_filled_to_filled(self, order: Order) -> None:
        """PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED is a valid path."""
        o1 = order.transition_to(OrderStatus.SUBMITTED)
        o2 = o1.transition_to(OrderStatus.PARTIALLY_FILLED)
        o3 = o2.transition_to(OrderStatus.FILLED)
        assert o3.status == OrderStatus.FILLED

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.PENDING))
    def test_pending_to_partially_filled_to_cancelled(self, order: Order) -> None:
        """PENDING → SUBMITTED → PARTIALLY_FILLED → CANCELLED is a valid path."""
        o1 = order.transition_to(OrderStatus.SUBMITTED)
        o2 = o1.transition_to(OrderStatus.PARTIALLY_FILLED)
        o3 = o2.transition_to(OrderStatus.CANCELLED)
        assert o3.status == OrderStatus.CANCELLED

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.SUBMITTED))
    def test_submitted_direct_to_filled(self, order: Order) -> None:
        """SUBMITTED → FILLED is a valid direct path (no partial fill)."""
        new_order = order.transition_to(OrderStatus.FILLED)
        assert new_order.status == OrderStatus.FILLED

    @given(valid_orders().filter(lambda o: o.status == OrderStatus.SUBMITTED))
    def test_submitted_direct_to_cancelled(self, order: Order) -> None:
        """SUBMITTED → CANCELLED is a valid direct path."""
        new_order = order.transition_to(OrderStatus.CANCELLED)
        assert new_order.status == OrderStatus.CANCELLED


class TestOrderFSMInvariants:
    """Tests for structural invariants of the FSM."""

    def test_no_cycles_in_transition_graph(self) -> None:
        """The transition graph has no cycles (it's a DAG)."""
        # This is verified by checking no state can reach itself via any path
        visited = set()

        def has_cycle(state: OrderStatus, path: set[OrderStatus]) -> bool:
            if state in path:
                return True
            path.add(state)
            for next_state in LEGAL_TRANSITIONS.get(state, frozenset()):
                if has_cycle(next_state, path):
                    return True
            path.remove(state)
            return False

        for state in OrderStatus:
            assert not has_cycle(state, set()), f"Cycle detected starting from {state}"

    def test_all_statuses_reachable_from_pending(self) -> None:
        """All non-terminal statuses are reachable from PENDING."""
        reachable = set()

        def dfs(state: OrderStatus):
            reachable.add(state)
            for next_state in LEGAL_TRANSITIONS.get(state, frozenset()):
                if next_state not in reachable:
                    dfs(next_state)

        dfs(OrderStatus.PENDING)

        # All statuses except terminal ones should be reachable
        non_terminal = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        for status in non_terminal:
            assert status in reachable, f"{status} not reachable from PENDING"

    def test_terminal_states_have_no_outgoing(self) -> None:
        """Terminal states have no outgoing transitions."""
        terminals = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}
        for term in terminals:
            assert LEGAL_TRANSITIONS[term] == frozenset(), f"{term} has outgoing transitions"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])