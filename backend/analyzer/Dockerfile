# LLM photo analyzer — production component, containerized.
# Build context = REPO ROOT (needs backend/common + backend/analyzer):
#   docker compose --profile analyzer up -d --build analyzer
FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /bin/uv

WORKDIR /app/analyzer

# deps from the analyzer's own pyproject (httpx, dotenv, sqlalchemy, asyncpg, geoalchemy2)
COPY backend/analyzer/pyproject.toml backend/analyzer/uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o /tmp/analyzer-requirements.txt \
    && uv pip install --system -r /tmp/analyzer-requirements.txt \
    && rm /tmp/analyzer-requirements.txt /bin/uv

RUN python -m pip uninstall --yes pip && python -c "import pathlib, sysconfig; [p.unlink() for p in (pathlib.Path(sysconfig.get_path('stdlib')) / 'ensurepip' / '_bundled').glob('pip-*.whl')]"

# the backend common package (models/database) — reached via PYTHONPATH, replacing
# the script's repo-layout sys.path hack (which becomes a harmless no-op in here)
COPY backend/common /app/backend/common
COPY backend/analyzer/*.py /app/analyzer/

ENV PYTHONPATH=/app/backend
ENV ANALYZER_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1001 analyzer && mkdir -p /data && chown analyzer /data
USER analyzer

# steady-state loop is built into analyzer.py (--sleep); restart policy covers crashes.
CMD ["python", "analyzer.py", "--verbose"]
