.PHONY: sync lint type test docs check ci

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

# Reproduces the CI workflow locally (.github/workflows/ci.yml): the same gates, the same pytest arguments
# (all non-live tests, slow included, under the network guard), and the same rule that any skipped test fails.
ci: lint type docs
	uv run python -m tracewise.bench verify
	@bash -c 'set -eo pipefail; out=$$(mktemp); trap "rm -f $$out" EXIT; \
	  PYTHONPATH=$(CURDIR) uv run pytest -q -p no:cacheprovider -p tests.netguard -m "not live" -rs | tee "$$out"; \
	  if grep -Eq "[0-9]+ skipped" "$$out"; then echo "tests were skipped: the CI gate requires every test to run" >&2; exit 1; fi'
