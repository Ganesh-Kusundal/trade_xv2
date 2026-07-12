"""Token Management Utilities for Dhan broker.

Provides TOTP token generation, env file updates, and secret reading
utilities used by the Dhan broker factory and token scheduler.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.dhan.config.settings import DhanConnectionSettings

logger = logging.getLogger(__name__)


def generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP (delegates to DhanTotpClient)."""
    from brokers.dhan.auth.totp_client import DhanTotpClient

    return DhanTotpClient(settings).generate()
