"""Dhan adapter test — skipped during broker module refactoring.

The ``DhanDataAdapter`` class was removed as part of the broker module
consolidation (Phase 9.x).  ``BrokerGateway`` now satisfies ``BrokerAdapter``
structurally; the separate adapter layer is no longer needed.
"""

import pytest

pytestmark = pytest.mark.skip(reason="DhanDataAdapter removed during broker module refactoring")
