"""brokers.common.auth — shared token lifecycle protocol and re-exports."""

from brokers.common.auth.lifecycle import (
    TokenLifecyclePort,
    merge_auth_error_detail,
    should_attempt_refresh,
)
from infrastructure.auth.token_lifecycle import TokenLifecycle

__all__ = [
    "TokenLifecycle",
    "TokenLifecyclePort",
    "merge_auth_error_detail",
    "should_attempt_refresh",
]
