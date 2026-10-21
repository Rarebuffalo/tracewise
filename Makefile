.PHONY: sync lint type test docs web web-e2e check ci image image-check

sync:
	uv sync

lint:
	uv run ruff check src tests scripts web
	uv run ruff format --check src tests scripts web

type:
	uv run mypy
	uv run mypy --strict scripts
	uv run mypy --strict web/site.py web/vercel_app.py

test:
	uv run pytest -m "not live and not slow"

test-all:
	uv run pytest -m "not live"

docs:
	python3 -I scripts/check_docs.py

# Website: zero-dependency build, then the browser-side unit tests and the build's own guarantees (Node >= 20).
web:
	node web/build.mjs
	node --test web/test/*.test.mjs

# Website end to end in headless Chromium: a disposable PostgreSQL, file-based email, the real app on 127.0.0.1.
web-e2e: web
	@bash -c 'set -eo pipefail; port=$${E2E_PORT:-8011}; mail=$$(mktemp -d); log=$$(mktemp); \
	  WAITLIST_EMAIL_FILE_DIR=$$mail PYTHONPATH=$(CURDIR) uv run python web/dev.py --port $$port >"$$log" 2>&1 & pid=$$!; \
	  trap "kill $$pid 2>/dev/null; wait $$pid 2>/dev/null || true; rm -rf $$mail $$log" EXIT; \
	  for i in $$(seq 1 100); do curl -fsS "http://127.0.0.1:$$port/api/waitlist/health" >/dev/null 2>&1 && break; sleep 0.2; done; \
	  E2E_BASE_URL=http://127.0.0.1:$$port E2E_MAIL_DIR=$$mail node web/test/e2e.mjs'

check: lint type test docs web

# Reproduces the CI workflow locally (.github/workflows/ci.yml): the same gates, the same pytest arguments
# (all non-live tests, slow included, under the network guard), and the same rule that any skipped test fails.
ci: lint type docs web
	uv run python -m tracewise.bench verify
	@bash -c 'set -eo pipefail; out=$$(mktemp); trap "rm -f $$out" EXIT; \
	  PYTHONPATH=$(CURDIR) uv run pytest -q -p no:cacheprovider -p tests.netguard -m "not live" -rs | tee "$$out"; \
	  if grep -Eq "[0-9]+ skipped" "$$out"; then echo "tests were skipped: the CI gate requires every test to run" >&2; exit 1; fi'

# Runtime image (T-1002): build it, then run every process from it against a disposable PostgreSQL, offline
# (containers use --network none). Needs Docker; not part of `ci`. See docs/DEPLOYMENT-BLUEPRINT.md §2a.
image:
	docker build -t tracewise:local .

image-check: image
	PYTHONPATH=$(CURDIR) uv run python scripts/container_check.py
