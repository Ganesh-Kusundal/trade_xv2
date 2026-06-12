"""Top-level conftest for the ``brokers.dhan.tests`` tree.

The actual ``instrument_service`` and ``real_csv_path`` fixtures live in
``brokers/dhan/tests/fixtures/conftest.py`` (per the plan: they belong
next to the fixture data).  Pytest only auto-loads conftest.py from
ancestor directories of each test, so we re-export the fixtures here so
tests in ``brokers/dhan/tests/unit/`` and
``brokers/dhan/tests/integration/`` can pick them up without each having
its own copy.

If you add a new fixture to ``fixtures/conftest.py``, you do **not**
need to touch this file — the ``*`` re-export below grabs them all.
"""

from brokers.dhan.tests.fixtures.conftest import *  # noqa: F403
