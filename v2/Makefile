.PHONY: install lint test cli

export PYTHONPATH := src

install:
	pip install -e ".[dev]"

lint:
	@if command -v ruff >/dev/null 2>&1; then ruff check src tests; else echo "ruff not installed — skip"; fi

test:
	PYTHONPATH=src python -m pytest tests/ -q

cli:
	PYTHONPATH=src python -m tradex.cli version
