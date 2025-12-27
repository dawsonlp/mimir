# PostgreSQL with pgvector extension
# Built from official postgres base for better security update cadence
FROM postgres:18

# Install pgvector extension for vector similarity search
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-18-pgvector && \
    rm -rf /var/lib/apt/lists/*

# Health check for container orchestration
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD pg_isready -U ${POSTGRES_USER:-mimir} -d ${POSTGRES_DB:-mimir}
