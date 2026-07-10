"""Backward-compat shim — ``read_secret`` now lives in ``brokers.dhan.auth.secret_utils``."""
from brokers.dhan.auth.secret_utils import read_secret  # noqa: F401
