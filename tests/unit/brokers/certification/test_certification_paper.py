"""Unit tests for broker certification modules."""

from __future__ import annotations

import pytest

from brokers.certification.golden import load_golden_cases, verify_golden
from brokers.certification.mapping import verify_mapping
from brokers.certification.suite import BrokerCertifier
from brokers.services.core import run_verify
from brokers.session import BrokerSession


@pytest.mark.unit
@pytest.mark.certification
def test_verify_mapping_paper() -> None:
    report = verify_mapping("paper")
    assert report.all_passed, report.results


@pytest.mark.unit
@pytest.mark.certification
def test_verify_golden_paper() -> None:
    report = verify_golden("paper")
    assert report.all_passed, report.results


@pytest.mark.unit
@pytest.mark.certification
def test_golden_dataset_loads() -> None:
    cases = load_golden_cases()
    assert len(cases) >= 3
    symbols = {c.symbol for c in cases}
    assert "RELIANCE" in symbols


@pytest.mark.unit
@pytest.mark.certification
def test_broker_certifier_paper() -> None:
    session = BrokerSession("paper")
    try:
        report = BrokerCertifier(session).certify()
    finally:
        session.close()
    assert report.is_certified, report.results


@pytest.mark.unit
@pytest.mark.certification
def test_run_verify_paper() -> None:
    report = run_verify("paper")
    assert report.passed, report.steps


@pytest.mark.unit
@pytest.mark.certification
def test_certifier_skips_stream_depth_off_market(monkeypatch: pytest.MonkeyPatch) -> None:
    from brokers.certification import suite as cert_suite

    monkeypatch.setattr(cert_suite, "is_nse_market_open", lambda: False)
    session = BrokerSession("paper")
    try:
        report = BrokerCertifier(session).certify()
    finally:
        session.close()
    depth = next(r for r in report.results if r.area.value == "Depth")
    stream = next(r for r in report.results if r.area.value == "Live Stream")
    assert depth.passed and "off-market" in depth.detail
    assert stream.passed and "off-market" in stream.detail


@pytest.mark.unit
@pytest.mark.certification
def test_broker_session_runtime_bundle() -> None:
    session = BrokerSession("paper")
    try:
        assert session.runtime is not None
        assert session.runtime.execution is not None
        stock = session.stock("RELIANCE")
        assert hasattr(stock, "history")
        assert hasattr(stock, "subscribe")
        assert hasattr(stock, "capabilities")
    finally:
        session.close()
