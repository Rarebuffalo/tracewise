.PHONY: sync lint type test docs check

sync:
	uv sync

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

type:
	uv run mypy
	uv run mypy --strict scripts

test:
	uv run pytest -m "not live and not slow"

test-all:
	uv run pytest -m "not live"

docs:
	python3 -I scripts/check_docs.py

check: lint type test docs
