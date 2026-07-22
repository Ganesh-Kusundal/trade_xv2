"""Unit tests for API order idempotency contract."""

from __future__ import annotations

import os

import pytest

from interface.api.order_idempotency import IDEMPOTENCY_HEADER, resolve_api_correlation_id


def test_body_correlation_id_wins():
    assert resolve_api_correlation_id("body-corr-1", "header-key") == "body-corr-1"


def test_header_used_when_body_missing():
    assert resolve_api_correlation_id(None, "header-key-99") == "header-key-99"


def test_missing_both_raises_outside_dev():
    with pytest.raises(ValueError, match="correlation_id"):
        resolve_api_correlation_id(None, None)


def test_dev_auto_correlation_when_tradex_dev(monkeypatch):
    monkeypatch.setenv("TRADEX_DEV", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    cid = resolve_api_correlation_id(None, None)
    assert cid.startswith("api:")


def test_idempotency_header_constant():
    assert IDEMPOTENCY_HEADER == "X-Idempotency-Key"
