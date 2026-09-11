# Panoramax federation read API. Build context is backend/ (like api and
# worker), same uv-export pattern as worker/Dockerfile.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /bin/uv

WORKDIR /app

# Workspace root + member pyproject files needed to resolve this package
COPY pyproject.toml uv.lock /app/
COPY common/pyproject.toml /app/common/
COPY panoramax/pyproject.toml /app/panoramax/

RUN uv export --frozen --no-hashes --no-emit-project --package hillview-panoramax | \
    grep -v "sys_platform == 'darwin'" | \
    sed "s/ ; sys_platform != 'darwin'//" > /tmp/requirements.txt && \
    uv pip install --system --no-deps -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

RUN groupadd --gid 1001 panoramax && \
    useradd --create-home --shell /bin/bash --uid 1001 --gid 1001 panoramax

COPY panoramax/app /app/app

RUN python -m compileall -b /app/app && chown -R panoramax:panoramax /app

USER panoramax
WORKDIR /app/app

ENV PYTHONPATH="/app/app:/app"

# 0.0.0.0, not "::": under uvloop (no --reload) a "::" bind is IPv6-only,
# which dead-ends the bridge-mode port mapping (docker-proxy connects over
# IPv4). External IPv6 is Caddy's job.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8058"]
