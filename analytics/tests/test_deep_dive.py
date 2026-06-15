"""Backward-compatible shim — imports all tests from focused modules."""

from .test_core import *  # noqa: F401,F403
from .test_reports import *  # noqa: F401,F403
from .test_options import *  # noqa: F401,F403
from .test_stocks import *  # noqa: F401,F403
from .test_scanner import *  # noqa: F401,F403
from .test_volume_profile import *  # noqa: F401,F403
from .test_volatility import *  # noqa: F401,F403
from .test_breadth import *  # noqa: F401,F403
from .test_orderflow import *  # noqa: F401,F403
from .test_visualizations import *  # noqa: F401,F403
from .test_features import *  # noqa: F401,F403
