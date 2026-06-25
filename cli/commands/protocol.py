"""CLI Command Protocol — type-safe interface for all commands.

All CLI commands MUST implement this protocol to ensure consistent
signatures and enable static type checking with mypy.

Usage::

    from cli.commands.protocol import CliCommand

    class MyCommand(CliCommand):
        def run(self, args: list[str], broker_service, console: Console) -> None:
            # Implementation
            pass
"""

from typing import Protocol

from rich.console import Console


class CliCommand(Protocol):
    """Protocol for all CLI command implementations.

    This protocol ensures that all CLI commands follow a consistent
    signature, enabling:
    - Static type checking with mypy
    - Consistent error handling patterns
    - Uniform argument passing
    - Standardized output via Rich console

    All commands in cli/commands/ should implement this interface.
    """

    def run(self, args: list[str], broker_service, console: Console) -> None:
        """Execute the command.

        Args:
            args: Command-line arguments (after the command name)
            broker_service: BrokerService instance for broker operations
            console: Rich console for formatted output
        """
        ...
