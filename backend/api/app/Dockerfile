FROM python:3.12-slim

# Install system dependencies
# Repair /tmp in the same layer as apt so _apt can create signature files.
RUN mkdir -p /tmp && chmod 1777 /tmp \
    && apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /bin/uv

WORKDIR /app

# Copy workspace root files
COPY pyproject.toml uv.lock /app/

# Copy workspace member pyproject.toml files
COPY common/pyproject.toml /app/common/
COPY api/app/pyproject.toml /app/api/app/

# Install API dependencies from workspace lockfile
RUN uv export --frozen --no-hashes --no-emit-project --package hillview-api | \
    grep -v "sys_platform == 'darwin'" | \
    sed "s/ ; sys_platform != 'darwin'//" > /tmp/requirements.txt && \
    uv pip install --system --no-deps -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Copy common directory
COPY common /app/common

# Copy API app directory
COPY api/app /app/app

# Set Python path to include app directory
ENV PYTHONPATH="/app/app:/app:$PYTHONPATH"

# Copy and setup prestart script
COPY api/app/prestart.sh /app/prestart.sh
RUN chmod +x /app/prestart.sh

# Run as non-root user (UID 1001, same as worker container)
RUN groupadd --gid 1001 api && useradd --create-home --shell /bin/bash --uid 1001 --gid 1001 api
RUN mkdir -p /app/uploads /app/pics && chown -R api:api /app/uploads /app/pics
USER api

# Default command (can be overridden by docker-compose)
CMD ["uvicorn", "api:app", "--host", "::", "--port", "8055"]
