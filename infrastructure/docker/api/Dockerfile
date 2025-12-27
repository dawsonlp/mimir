# Mímir API - Multi-stage build
# SECURITY: No secrets in image - all credentials provided at runtime

# Build stage - export dependencies
FROM python:3.13-slim AS builder
WORKDIR /app

# Install Poetry for dependency export
RUN pip install --no-cache-dir poetry

# Copy only dependency files first (better layer caching)
COPY pyproject.toml poetry.lock* ./

# Export dependencies to requirements.txt (without dev dependencies)
RUN poetry export -f requirements.txt -o requirements.txt --without-hashes

# Runtime stage - lean production image
FROM python:3.13-slim
WORKDIR /app

# Install dependencies only
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only (no config files with secrets)
COPY src/ ./src/
COPY migrations/ ./migrations/

# Set Python path for src layout
ENV PYTHONPATH=/app/src

# No default environment variables with secrets
# All credentials provided at runtime via docker-compose or orchestrator

EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "mimir.main:app", "--host", "0.0.0.0", "--port", "8000"]
