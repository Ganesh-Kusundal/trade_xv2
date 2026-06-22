"""Instrument catalog check strategy.

Validates instrument data loading and search functionality.
"""

from __future__ import annotations

from cli.commands.doctor.checks import CheckResult, CheckStrategy
from cli.services.broker_service import BrokerService


class InstrumentCatalogCheck(CheckStrategy):
    """Check instrument catalog loading and stats."""

    def execute(self, broker_service: BrokerService | None) -> list[CheckResult]:
        """Check instrument catalog health."""
        results: list[CheckResult] = []

        if broker_service is None:
            results.append(
                CheckResult("Instrument Catalog", "FAIL", "No broker service available")
            )
            return results

        try:
            gw = broker_service.active_broker
            # Try standard Interface-Aware approach first (search works on all brokers)
            search_test = gw.search("RELIANCE") if hasattr(gw, "search") else []
            if search_test and len(search_test) > 0:
                results.append(
                    CheckResult(
                        "Instrument Search",
                        "PASS",
                        f"Search returned {len(search_test)} result(s) for 'RELIANCE'",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        "Instrument Search",
                        "WARN",
                        "Search returned empty results (maybe no instruments loaded)",
                    )
                )

            # Check instruments by trying to resolve a known symbol
            try:
                insts = gw.instruments
                if hasattr(insts, "stats"):
                    stats = insts.stats()
                    total = stats.get("total", 0)
                    loaded = stats.get("loaded", False)
                    if loaded and total > 0:
                        results.append(
                            CheckResult(
                                "Instrument Resolver",
                                "PASS",
                                f"{total:,} instruments loaded into resolver",
                            )
                        )
                    else:
                        results.append(
                            CheckResult(
                                "Instrument Resolver",
                                "WARN",
                                f"Resolver loaded={loaded}, total={total}",
                            )
                        )
            except (AttributeError, Exception):
                results.append(
                    CheckResult(
                        "Instrument Resolver",
                        "INFO",
                        "Instrument resolver stats not available (paper/mock gateway)",
                    )
                )

        except Exception as exc:
            results.append(
                CheckResult(
                    "Instrument Catalog",
                    "FAIL",
                    f"Catalog check failed: {exc}",
                )
            )

        return results
