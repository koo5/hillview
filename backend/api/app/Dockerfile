FROM python:3.12-slim

RUN mkdir -p /tmp
RUN chmod 1777 /tmp

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

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

# Default command (can be overridden by docker-compose)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8055"]
