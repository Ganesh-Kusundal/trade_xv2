"""tradex.cli — unified CLI package.

Re-exports the ``tradex`` Click group so ``tradex.cli:tradex`` (the
``[project.scripts]`` entry point in ``pyproject.toml``) and
``from tradex.cli import tradex`` both keep resolving after the
single-file-to-package restructure.
"""

from __future__ import annotations

from tradex.cli.app import tradex

__all__ = ["tradex"]
