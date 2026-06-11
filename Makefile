.PHONY: install test lint format typecheck check run clean

install:
	uv sync --all-extras

test:
	uv run pytest

lint_fix:
	uv run ruff check . --fix && uv run ruff format . 

typecheck:
	uv run ty check

check: lint typecheck test

run:
	uv run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
