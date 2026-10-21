# Tracewise runtime image (T-1002). Vendor-neutral OCI image; builds the locked dependency set, no secrets.
# One image, one process per container; choose the process with the command (docs/DEPLOYMENT-BLUEPRINT.md §2):
#   web:       uvicorn --factory tracewise.web.asgi:create_runtime_app --host 0.0.0.0 --port 8000
#   worker:    python -m tracewise.worker
#   migrate:   python -m tracewise.db.migrate upgrade        (owner credentials only, one-off before a release)
#   preflight: python -m tracewise.preflight --process all --database
#   jobs:      python -m tracewise.recovery deliveries|runs, python -m tracewise.retention, python -m tracewise.ops alerts
# Secrets come from the platform at run time (environment and a mounted 0600 key file), never from the build.

FROM ghcr.io/astral-sh/uv:0.11.3 AS uv

FROM python:3.14-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-bookworm
# git: the worker's code context (falls back to the slower contents API without it).
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin tracewise
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 10001
WORKDIR /tmp
EXPOSE 8000
# No default process: running the image without a command only prints the preflight usage.
CMD ["python", "-m", "tracewise.preflight", "--help"]
