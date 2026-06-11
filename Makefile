.PHONY: install test lint format typecheck check run clean

install:
	uv sync --all-extras

test:
	uv run pytest

lint:
	uv run ruff check .

lint_fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

typecheck:
	uv run ty check

check: lint typecheck test

run:
	uv run python -m t3

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
