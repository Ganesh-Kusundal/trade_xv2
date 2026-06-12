from collections.abc import Callable


class Event:
    def __init__(self, event_id: str, payload: str):
        self.event_id = event_id
        self.payload = payload


class EventBus:
    """Mock Event Bus for isolation testing of delivery guarantees and ordering."""

    def __init__(self, max_capacity: int = 5):
        self.max_capacity = max_capacity
        self.queue: list[Event] = []
        self.subscribers: list[Callable[[Event], None]] = []
        self.processed_ids: dict[str, bool] = {}
        self.retry_queue: list[Event] = []

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        self.subscribers.append(callback)

    def publish(self, event: Event) -> bool:
        # Backpressure: reject if queue exceeds max capacity
        if len(self.queue) >= self.max_capacity:
            return False

        # Deduplication: discard duplicate event IDs
        if event.event_id in self.processed_ids:
            return True  # Ignored but returns True to signify no backpressure error

        self.queue.append(event)
        self.processed_ids[event.event_id] = True
        return True

    def process_next(self) -> bool:
        if not self.queue:
            return False

        event = self.queue.pop(0)  # FIFO ordering

        success = True
        for sub in self.subscribers:
            try:
                sub(event)
            except Exception:
                success = False

        if not success:
            # Add to retry queue on failure
            self.retry_queue.append(event)

        return True

    def process_retries(self) -> None:
        while self.retry_queue:
            event = self.retry_queue.pop(0)
            # Re-publish or attempt processing
            for sub in self.subscribers:
                try:
                    sub(event)
                except Exception:
                    # Put back on retry if it fails again
                    self.retry_queue.append(event)
                    break


# ── Tests ──────────────────────────────────────────────────────────────────


def test_event_bus_fifo_ordering_and_delivery():
    bus = EventBus()
    received: list[str] = []

    bus.subscribe(lambda e: received.append(e.payload))

    bus.publish(Event("E1", "Message 1"))
    bus.publish(Event("E2", "Message 2"))
    bus.publish(Event("E3", "Message 3"))

    # Process FIFO
    bus.process_next()
    assert received == ["Message 1"]

    bus.process_next()
    bus.process_next()
    assert received == ["Message 1", "Message 2", "Message 3"]


def test_event_deduplication():
    bus = EventBus()
    received: list[str] = []

    bus.subscribe(lambda e: received.append(e.payload))

    # Publish E1 twice
    bus.publish(Event("E1", "Message 1"))
    bus.publish(Event("E1", "Message 1 Duplicate"))

    bus.process_next()
    bus.process_next()  # Nothing left in queue if duplicate was skipped

    assert received == ["Message 1"]


def test_retry_mechanism_on_failure():
    bus = EventBus()
    attempts = 0

    def failing_subscriber(event: Event):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("Temporary delivery failure")

    bus.subscribe(failing_subscriber)
    bus.publish(Event("E1", "Message 1"))

    # First attempt fails -> goes to retry queue
    bus.process_next()
    assert len(bus.retry_queue) == 1

    # Process retries -> succeeds on second attempt
    bus.process_retries()
    assert len(bus.retry_queue) == 0
    assert attempts == 2


def test_backpressure_rejection():
    bus = EventBus(max_capacity=2)

    assert bus.publish(Event("E1", "Msg 1")) is True
    assert bus.publish(Event("E2", "Msg 2")) is True

    # 3rd message rejected due to full queue
    assert bus.publish(Event("E3", "Msg 3")) is False
