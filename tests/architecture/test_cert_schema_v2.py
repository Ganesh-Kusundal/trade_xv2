"""TRANS-P4-003 — verify + certify JSON schema v2 validated in CI (ADR-018)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.certification.report import CertificationReport
from brokers.certification.schema_v2 import (
    SCHEMA_VERSION,
    validate_certification_report,
    validate_verify_report,
)
from brokers.certification.suite import BrokerCertifier
from brokers.services.core import VerifyReport, run_verify
from brokers.session import BrokerSession


@pytest.mark.architecture
def test_verify_report_schema_v2_paper() -> None:
    report = run_verify("paper")
    data = report.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["tier"] == "L1"
    assert data["status"] in {"passed", "failed", "blocked"}
    errors = validate_verify_report(data)
    assert errors == [], errors


@pytest.mark.architecture
def test_certification_report_schema_v2_paper() -> None:
    def _mock_opener(_broker_id: str, **_kwargs):
        return MagicMock()

    with patch("runtime.session_opener._session_opener", _mock_opener):
        session = BrokerSession("paper")
        try:
            report = BrokerCertifier(session).certify()
        finally:
            session.close()
    data = report.to_dict()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["tier"] == "L1"
    errors = validate_certification_report(data)
    assert errors == [], errors


@pytest.mark.architecture
def test_verify_report_rejects_incomplete_dict() -> None:
    errors = validate_verify_report({"broker_id": "paper"})
    assert any("missing keys" in e for e in errors)


@pytest.mark.architecture
def test_cert_report_live_tier() -> None:
    report = CertificationReport("dhan")
    data = report.to_dict(live=True)
    assert data["tier"] == "L3"


@pytest.mark.architecture
def test_verify_report_manual_dict_valid() -> None:
    report = VerifyReport(broker_id="paper")
    report.add("Configuration", True)
    report.certified = True
    data = report.to_dict()
    assert validate_verify_report(data) == []
