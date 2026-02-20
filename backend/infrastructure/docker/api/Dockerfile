# Mímir V4 API - Multi-stage build with uv
# SECURITY: No secrets in image - all credentials provided at runtime

# ── Build stage ──────────────────────────────────────────────
FROM python:3.13-slim AS builder
WORKDIR /app

# Install uv (fast Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create venv for clean dependency isolation
RUN uv venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy project metadata + source
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package + production deps into venv (single shot)
# Registers importlib.metadata AND installs all dependencies
RUN uv pip install --no-cache .

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.13-slim AS runtime
WORKDIR /app

# Copy the fully-built venv (deps + installed package + metadata)
COPY --from=builder /app/.venv /app/.venv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy non-Python artifacts (migrations, static files, etc.)
COPY migrations/ ./migrations/

# No PYTHONPATH needed - mimir is properly installed in the venv
# No default environment variables with secrets
# All credentials provided at runtime via docker-compose or orchestrator

EXPOSE 8000

# Health check for container orchestration (uses Python stdlib - no curl needed)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["python", "-m", "mimir.healthcheck"]

CMD ["uvicorn", "mimir.main:app", "--host", "0.0.0.0", "--port", "8000"]