# Terrain render worker — containerized twin of run_worker.sh (which remains
# the host-side option for fine ČÚZK mosaics living outside docker). Deps are
# the same hash-pinned lock; rendering uses rasterio's bundled GDAL. gdal-bin
# is only for gdalbuildvrt in the entrypoint's auto-DSM path.
FROM python:3.12-slim

# gdal-bin: gdalbuildvrt/gdalwarp for the auto-DSM paths. Rendering itself
# uses rasterio's own GDAL.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# pdal (ČÚZK LAZ rasterization, auto_cuzk.sh) is packaged by NEITHER Debian
# nor Ubuntu — conda-forge via micromamba, in its own prefix. PATH-APPENDED so
# the conda env's python never shadows the image python (hash-locked pip env).
RUN curl -L -o /usr/local/bin/micromamba \
        https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64 \
    && chmod +x /usr/local/bin/micromamba \
    && micromamba create -y -p /opt/pdal -c conda-forge pdal \
    && micromamba clean -a -y
ENV PATH="$PATH:/opt/pdal/bin"

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY renderer.py worker.py download_glo30.py download_cuzk.py build_mosaic.py \
     auto_cuzk.sh docker-entrypoint.sh ./

# /dem is a volume (compose: terrain_dem) — tiles survive image rebuilds
ENTRYPOINT ["sh", "docker-entrypoint.sh"]
