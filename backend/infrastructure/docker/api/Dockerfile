# Mímir V4 API - Multi-stage build
# SECURITY: No secrets in image - all credentials provided at runtime

# Build stage - install dependencies and register package metadata
FROM python:3.13-slim AS builder
WORKDIR /app

# Install Poetry for dependency resolution
RUN pip install --no-cache-dir poetry

# Copy only dependency files first (better layer caching)
COPY pyproject.toml ./

# Configure poetry to install deps globally (no virtualenv in container)
RUN poetry config virtualenvs.create false

# Install dependencies without dev packages (--no-root skips project package)
RUN poetry install --only main --no-interaction --no-root

# Copy source code and install the root package (registers importlib.metadata)
# This is required so importlib.metadata.version("mimir") returns the correct version
COPY src/ ./src/
RUN poetry install --only-root --no-interaction

# Runtime stage - lean production image
FROM python:3.13-slim AS runtime
WORKDIR /app

# Copy installed packages from builder stage (includes deps + mimir package metadata)
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code - src contents become the deployed package structure
# (src/ is the sources root, not a package - only its contents are deployed)
# PYTHONPATH=/app ensures this copy is used for imports (takes precedence over site-packages)
COPY src/mimir/ ./mimir/
COPY migrations/ ./migrations/

# PYTHONPATH points to workdir where mimir/ package now lives
ENV PYTHONPATH=/app

# No default environment variables with secrets
# All credentials provided at runtime via docker-compose or orchestrator

EXPOSE 8000

# Health check for container orchestration (uses Python stdlib - no curl needed)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD ["python", "-m", "mimir.healthcheck"]

CMD ["uvicorn", "mimir.main:app", "--host", "0.0.0.0", "--port", "8000"]