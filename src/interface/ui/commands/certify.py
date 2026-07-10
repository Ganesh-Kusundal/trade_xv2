"""CLI command: tradex certify <broker> [--live] [--json]"""

from __future__ import annotations

import json

import click


@click.command()
@click.argument("broker_id", type=click.Choice(["dhan", "upstox", "paper"]))
@click.option("--live", is_flag=True, help="Run live API tests (requires .env.local)")
@click.option("--json", "json_output", is_flag=True, help="Output JSON report")
def certify(broker_id: str, live: bool, json_output: bool) -> None:
    """Run broker certification suite.

    Runs comprehensive contract tests for the specified broker and produces
    a pass/fail certification report.

    Examples:
        tradex certify dhan
        tradex certify upstox --live
        tradex certify paper --json
    """
    from brokers.common.tests.certify_broker import run_certification  # sanctioned — broker test harness

    report = run_certification(broker_id, live_mode=live)

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        report.print_report()

    if not report.is_certified:
        click.echo("Certification FAILED. Review the report above for details.", err=True)
        raise SystemExit(1)
    else:
        click.echo("Certification PASSED. Broker meets all contract requirements.")
