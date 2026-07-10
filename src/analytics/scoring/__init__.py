"""Scoring — probability + ranking consolidated entry point.

    from analytics.scoring import ...
"""

from __future__ import annotations

# Re-export public surfaces from the former tiny packages.
try:
    from analytics.probability import *  # noqa: F401, F403
except ImportError:
    pass

try:
    from analytics.ranking import *  # noqa: F401, F403
except ImportError:
    pass
