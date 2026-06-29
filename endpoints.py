"""Backward-compat shim — moved to config.endpoints.

Canonical location: config/endpoints.py
All new code should import from config.endpoints instead.
"""
from config.endpoints import *  # noqa: F403
from config.endpoints import _UpstoxUrls  # noqa: F401
