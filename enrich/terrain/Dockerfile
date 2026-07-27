# Terrain render worker — containerized twin of run_worker.sh (which remains
# the host-side option for fine ČÚZK mosaics living outside docker). Deps are
# the same hash-pinned lock; rendering uses rasterio's bundled GDAL. gdal-bin
# is only for gdalbuildvrt in the entrypoint's auto-DSM path.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY renderer.py worker.py download_glo30.py docker-entrypoint.sh ./

# /dem is a volume (compose: terrain_dem) — tiles survive image rebuilds
ENTRYPOINT ["sh", "docker-entrypoint.sh"]
