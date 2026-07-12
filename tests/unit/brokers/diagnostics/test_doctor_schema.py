"""Unified doctor JSON schema (TRANS-P4-002)."""

from __future__ import annotations

import pytest

from brokers.diagnostics.core import CheckResult, CheckStatus
from brokers.diagnostics.doctor import DoctorReport, run_doctor
from brokers.diagnostics.schema import DOCTOR_SCHEMA_VERSION, format_doctor_dict


@pytest.mark.unit
def test_doctor_schema_has_required_fields() -> None:
    payload = format_doctor_dict(
        broker_id="paper",
        checks=[CheckResult("Auth", CheckStatus.PASS, "ok")],
        mode="sim",
    )
    assert payload["schema_version"] == DOCTOR_SCHEMA_VERSION
    assert payload["command"] == "doctor"
    assert payload["broker"] == "paper"
    assert payload["overall"] in {"passed", "failed", "blocked"}
    assert payload["checks"][0]["id"] == "Auth"
    assert payload["checks"][0]["status"] == "passed"
    assert "environment" in payload


@pytest.mark.unit
def test_warning_maps_to_blocked_overall() -> None:
    payload = format_doctor_dict(
        broker_id="paper",
        checks=[CheckResult("WS", CheckStatus.WARNING, "off-market")],
    )
    assert payload["overall"] == "blocked"
    assert payload["checks"][0]["status"] == "blocked"


@pytest.mark.unit
def test_run_doctor_paper_emits_schema() -> None:
    report = run_doctor("paper")
    data = report.to_dict(mode="sim")
    assert data["schema_version"] == DOCTOR_SCHEMA_VERSION
    assert data["broker"] == "paper"
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) >= 3


@pytest.mark.unit
def test_doctor_report_overall_property() -> None:
    report = DoctorReport("paper")
    report.add("A", CheckStatus.PASS, "ok")
    assert report.overall == "passed"