"""AppConfig schema validation."""

import pytest
from pydantic import ValidationError

from config.schema import AppConfig


def test_invalid_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        AppConfig(environment="STAGING")


def test_valid_paper_ok() -> None:
    cfg = AppConfig(environment="PAPER")
    assert cfg.environment == "PAPER"
