"""Append-only audit sink."""

from infrastructure.observability.audit import AuditSink


def test_record_appends() -> None:
    sink = AuditSink()
    sink.record({"event_type": "ORDER_SUBMITTED", "actor": "oms"})
    sink.record({"event_type": "FILL", "actor": "execution"})
    assert len(sink.records) == 2
    assert sink.records[0]["event_type"] == "ORDER_SUBMITTED"
    assert sink.records[1]["event_type"] == "FILL"


def test_records_is_append_only_view() -> None:
    sink = AuditSink()
    sink.record("a")
    view = sink.records
    view.append("mutated")  # must not affect sink
    assert sink.records == ["a"]
