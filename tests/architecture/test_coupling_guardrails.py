"""Architecture tests — prevent regression of shotgun-surgery / coupling fixes.

Guards the REF-1..REF-10 structural cleanup (see
docs/architecture/SHOTGUN-SURGERY-AUDIT.md):

* REF-1/REF-10: symbol/string normalization routes through
  ``domain.symbols`` / ``domain.normalize`` — no ad-hoc ``upper().strip()``
  outside those modules.
* REF-2: slippage applied via ``domain.trading_costs.apply_slippage`` only —
  no inline ``price * (1 +/- slippage`` arithmetic.
* REF-3: single backoff source — ``brokers.common.backoff`` deleted.
* REF-6: exactly one ``create_trading_context`` builder
  (``application.oms.factory``), not a duplicate in ``domain``.
* REF-7: no docstring-only stub inviting application->infrastructure import.
"""

from __future__ import annotations

import os
import subprocess

import pytest

_SRC = "src"
# Layers that must NOT contain ad-hoc ``upper().strip()`` / ``strip().upper()``
# (REF-1/REF-10). ``domain`` is the normalization authority and may normalize
# its own internal fields; ``datalake/core/symbols.py`` re-exports domain helpers.
_NON_NORMALIZER_LAYERS = (
    "src/brokers",
    "src/interface",
    "src/infrastructure",
    "src/application",
    "src/plugins",
    "src/analytics",
    "src/runtime",
    "src/tradex",
)


def _grep(pattern: str, paths: list[str]) -> list[str]:
    """Run grep and return matching lines (excluding ``# noqa``)."""
    result = subprocess.run(
        ["grep", "-rnE", "--include=*.py", pattern, *paths],
        capture_output=True, text=True,
    )
    return [
        line for line in result.stdout.strip().split("\n")
        if line and "# noqa" not in line
    ]


@pytest.mark.architecture
def test_no_adhoc_normalization_outside_normalizers():
    """REF-1/REF-10: no ad-hoc ``upper().strip()`` / ``strip().upper()`` outside domain."""
    hits = _grep(r"\.upper\(\)\.strip\(\)|\.strip\(\)\.upper\(\)", list(_NON_NORMALIZER_LAYERS))
    assert not hits, (
        "Ad-hoc string normalization found outside domain normalizers (SMELL-10) "
        "— route through domain.normalize.normalize_text:\n"
        + "\n".join(f"  {h}" for h in hits)
    )


@pytest.mark.architecture
def test_no_inline_slippage_outside_trading_costs():
    """REF-2: slippage must go through domain.trading_costs.apply_slippage."""
    hits = _grep(r"\*\s*\(1\s*[+-]\s*slippage", [_SRC])
    assert not hits, (
        "Inline slippage arithmetic found (SMELL-2) — use domain.trading_costs.apply_slippage:\n"
        + "\n".join(f"  {h}" for h in hits)
    )


@pytest.mark.architecture
def test_no_brokers_common_backoff():
    """REF-3: brokers.common.backoff deleted; backoff lives in infrastructure.resilience."""
    hits = _grep(r"brokers\.common\.backoff", [_SRC])
    assert not hits, (
        "brokers.common.backoff still referenced (SMELL-3):\n"
        + "\n".join(f"  {h}" for h in hits)
    )


@pytest.mark.architecture
def test_single_create_trading_context_builder():
    """REF-6: exactly one create_trading_context definition, in application.oms.factory."""
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", r"def create_trading_context(", _SRC],
        capture_output=True, text=True,
    )
    defs = [
        line for line in result.stdout.strip().split("\n")
        if line and "/tests/" not in line and "# noqa" not in line
    ]
    canonical = [d for d in defs if "application/oms/factory.py" in d]
    stray = [d for d in defs if "application/oms/factory.py" not in d]
    assert canonical, "create_trading_context builder missing from application/oms/factory.py"
    assert not stray, (
        "Stray create_trading_context definition (SMELL-6):\n"
        + "\n".join(f"  {s}" for s in stray)
    )


@pytest.mark.architecture
def test_no_historical_data_stub():
    """REF-7: application/services/historical_data.py stub deleted."""
    stub = os.path.join(_SRC, "application", "services", "historical_data.py")
    assert not os.path.exists(stub), (
        "application/services/historical_data.py still exists — it is a docstring-only "
        "stub that invites application->infrastructure imports (SMELL-7)."
    )
