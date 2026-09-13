# LLM photo analyzer — production component, containerized.
# Build context = REPO ROOT (needs backend/common + scripts/analyzer):
#   docker compose --profile analyzer up -d --build analyzer
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.5 /uv /bin/uv

WORKDIR /app/analyzer

# deps from the analyzer's own pyproject (httpx, dotenv, sqlalchemy, asyncpg, geoalchemy2)
COPY scripts/analyzer/pyproject.toml ./
RUN uv pip install --system -r pyproject.toml

# the backend common package (models/database) — reached via PYTHONPATH, replacing
# the script's repo-layout sys.path hack (which becomes a harmless no-op in here)
COPY backend/common /app/backend/common
COPY scripts/analyzer/*.py /app/analyzer/

ENV PYTHONPATH=/app/backend
ENV ANALYZER_DATA_DIR=/data

RUN useradd --create-home --uid 1001 analyzer && mkdir -p /data && chown analyzer /data
USER analyzer

# steady-state loop is built into analyzer.py (--sleep); restart policy covers crashes.
CMD ["python", "analyzer.py", "--verbose"]
