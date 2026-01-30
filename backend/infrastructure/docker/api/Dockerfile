# Mímir V2 API - Multi-stage build
# SECURITY: No secrets in image - all credentials provided at runtime

# Build stage - install dependencies
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

# Set Python path for src layout (needed when builder stage used directly in dev)
ENV PYTHONPATH=/app/src

# Runtime stage - lean production image
FROM python:3.13-slim AS runtime
WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code - src contents become the deployed package structure
# (src/ is the sources root, not a package - only its contents are deployed)
COPY src/mimir/ ./mimir/
COPY migrations/ ./migrations/

# PYTHONPATH points to workdir where mimir/ package now lives
ENV PYTHONPATH=/app

# No default environment variables with secrets
# All credentials provided at runtime via docker-compose or orchestrator

EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "mimir.main:app", "--host", "0.0.0.0", "--port", "8000"]
