"""Backward-compat entry: ``python -m cli`` → ``interface.ui.main``."""

from __future__ import annotations

from interface.ui.main import main

if __name__ == "__main__":
    main()
